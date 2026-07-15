"""
Language-ID Router — 以 facebook/mms-lid-4017 判斷逐段語言，決定台語段落走 Breeze-ASR-26。

背景：主轉錄一律以 Breeze-ASR-25（華語）跑。舊 Plan B 以 `avg_logprob` 低信心當「可能
非華語」的**代理指標**再用 Breeze-26 補；此代理不精準（低信心可能只是雜訊/口音）。
本模組改以真正的**語言辨識**判斷：對每個 ASR-25 段落跑 MMS-LID（Wav2Vec2 分類，4017 語言、
ISO 639-3），偵測為台語（`nan`，Min Nan）者才路由到 Breeze-26，其餘維持 Breeze-25。

效能：一次載入整個 chunk 音檔為 numpy，於記憶體切片（免逐段 ffmpeg），批次推論 LID；
只有被判為台語的少數段落才做較貴的 Breeze-26 重轉。

依賴：transformers>=4.30、torch、torchaudio（community-1 影像經 whisperx 已具備 transformers）。
模型於首次使用時 lazy-load（與 Breeze-26 相同模式），公開模型免 HF token。
"""

from __future__ import annotations

import os
import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

LID_MODEL_ID = os.getenv("LID_MODEL_ID", "facebook/mms-lid-4017")
# 判為「台語」而路由到 Breeze-26 的語言碼集合（ISO 639-3，逗號分隔，可 env 覆寫）
TAIWANESE_LANGS = set(
    x.strip() for x in os.getenv("LID_TAIWANESE_LANGS", "nan").split(",") if x.strip()
)
# LID 機率下限：top-1 判為台語且機率達此值 → 路由（高精準路徑）
LID_MIN_PROB = float(os.getenv("LID_MIN_PROB", "0.5"))
# 台語「絕對機率下限」：即使 top-1 是華語，只要 nan 的機率 ≥ 此值也路由。預設 1.1＝停用。
# （實測 nan 機率被稀釋，此路徑效果有限；主要 recall 靠下方 top-k。）
LID_TW_PROB_FLOOR = float(os.getenv("LID_TW_PROB_FLOOR", "1.1"))
# 台語 top-k 路由：nan 出現在 LID 前 K 名即路由到 Breeze-26。0＝停用。
# 實測（TaigiSpeech vs uat03 華語）：nan∈top3 → 台語 recall 7/12(58%)、華語誤判 1/157(0.6%)，
# 遠優於 top-1（recall 1/12）。故預設 3。設 1 等效嚴格 top-1、0 停用。
LID_TW_TOPK = int(os.getenv("LID_TW_TOPK", "3"))
# 太短的段落 LID 不可靠，跳過（秒）
LID_MIN_CLIP_S = float(os.getenv("LID_MIN_CLIP_S", "1.0"))
# 送入 LID 的每段最長秒數（截斷，控記憶體/延遲；語言判斷不需整段）
LID_MAX_CLIP_S = float(os.getenv("LID_MAX_CLIP_S", "10.0"))
LID_BATCH = int(os.getenv("LID_BATCH", "8"))
# 閉集重正規化：把 MMS-LID 機率遮罩到「這場會議可能出現的語言」再重算 argmax/top-k。
# 第一性原理：softmax 攤在 4017 類，台語(nan)機率被近親漢語(cmn/yue/hak/wuu…)稀釋；
# 限縮到 {cmn,nan,eng} 後 nan 只需和華語一對一比，直接解稀釋 root cause。
# 逗號分隔 ISO 639-3；空字串＝停用（維持全 4017 類）。
LID_ALLOWED_LANGS = [
    x.strip() for x in os.getenv("LID_ALLOWED_LANGS", "cmn,nan,eng").split(",") if x.strip()
]
# 閉集模式下的 nan 路由門檻（重正規化後機率）。需以實測校準；預設 0.35 為起點。
LID_CS_NAN_PROB = float(os.getenv("LID_CS_NAN_PROB", "0.35"))
SR = 16000

_lid_model = None
_lid_extractor = None


def _load_lid():
    """Lazy-load MMS-LID model + feature extractor。"""
    global _lid_model, _lid_extractor
    if _lid_model is not None:
        return _lid_model, _lid_extractor

    from transformers import Wav2Vec2ForSequenceClassification, AutoFeatureExtractor
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[LID] Loading {LID_MODEL_ID} (device={device})")
    _lid_extractor = AutoFeatureExtractor.from_pretrained(LID_MODEL_ID)
    _lid_model = Wav2Vec2ForSequenceClassification.from_pretrained(LID_MODEL_ID)
    _lid_model.to(device)
    _lid_model.eval()
    logger.info(
        f"[LID] Loaded. classes={_lid_model.config.num_labels}, "
        f"taiwanese_langs={sorted(TAIWANESE_LANGS)}"
    )
    return _lid_model, _lid_extractor


def _clip(audio: np.ndarray, start_s: float, end_s: float, sr: int) -> np.ndarray:
    i0 = max(0, int(round(start_s * sr)))
    i1 = min(len(audio), int(round(end_s * sr)))
    # 截斷過長段落（僅取前 LID_MAX_CLIP_S 秒作語言判斷）
    i1 = min(i1, i0 + int(round(LID_MAX_CLIP_S * sr)))
    return audio[i0:i1]


def classify_spans(
    audio: np.ndarray,
    spans: List[Tuple[float, float]],
    sr: int = SR,
) -> List[Optional[dict]]:
    """對每個 (start_s, end_s) 回傳 dict{top_lang, top_prob, nan_prob, top3}；太短/失敗回 None。

    以記憶體切片 + 批次推論，避免逐段 ffmpeg。額外回傳 nan 的絕對機率與 top-3，
    供 recall 診斷與「絕對機率下限」路由。
    """
    results: List[Optional[dict]] = [None] * len(spans)
    # 收集夠長的候選
    cand_idx, clips = [], []
    for i, (s, e) in enumerate(spans):
        if e - s < LID_MIN_CLIP_S:
            continue
        c = _clip(audio, s, e, sr)
        if c.size < int(LID_MIN_CLIP_S * sr):
            continue
        cand_idx.append(i)
        clips.append(c.astype(np.float32))

    if not clips:
        return results

    model, extractor = _load_lid()
    import torch
    device = next(model.parameters()).device
    id2label = model.config.id2label
    label2id = {v: k for k, v in id2label.items()}
    nan_ids = [label2id[l] for l in TAIWANESE_LANGS if l in label2id]

    # 閉集重正規化：預先算允許類的索引（保留原始 id2label 以利診斷 nan_prob）
    allowed_ids = [label2id[l] for l in LID_ALLOWED_LANGS if l in label2id]
    if LID_ALLOWED_LANGS and not allowed_ids:
        logger.warning("[LID] LID_ALLOWED_LANGS=%s 皆不在模型標籤中，停用閉集", LID_ALLOWED_LANGS)
    use_closed_set = bool(allowed_ids)
    if use_closed_set:
        logger.info("[LID] closed-set renormalization on: %s", LID_ALLOWED_LANGS)

    nan_prob_summary = []
    for b in range(0, len(clips), LID_BATCH):
        batch = clips[b:b + LID_BATCH]
        idxs = cand_idx[b:b + LID_BATCH]
        inputs = extractor(batch, sampling_rate=sr, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        # 閉集：把非允許類的機率歸零後 renormalize，argmax/top-k 只在允許類間比較。
        # nan_prob 仍以「全 4017 類」的原始機率回報，作為未受閉集影響的診斷值。
        full_probs = probs
        if use_closed_set:
            mask = torch.zeros_like(probs)
            mask[:, allowed_ids] = 1.0
            probs = probs * mask
            probs = probs / (probs.sum(dim=-1, keepdim=True) + 1e-9)
        top_p, top_i = probs.max(dim=-1)
        topk_p, topk_i = torch.topk(probs, k=min(5, probs.shape[-1]), dim=-1)
        for j, orig_i in enumerate(idxs):
            top_lang = id2label[int(top_i[j].item())]
            top_prob = float(top_p[j].item())
            nan_prob = max((float(full_probs[j, nid].item()) for nid in nan_ids), default=0.0)
            nan_prob_cs = max((float(probs[j, nid].item()) for nid in nan_ids), default=0.0)
            topk = [(id2label[int(topk_i[j, r].item())], round(float(topk_p[j, r].item()), 3))
                    for r in range(topk_i.shape[-1])]
            results[orig_i] = {"top_lang": top_lang, "top_prob": top_prob,
                               "nan_prob": nan_prob, "nan_prob_cs": nan_prob_cs,
                               "top3": topk[:3], "topk": topk}
            nan_prob_summary.append(nan_prob)

    # recall 診斷摘要
    if nan_prob_summary:
        import numpy as _np
        arr = _np.array(nan_prob_summary)
        arr_cs = _np.array([r.get("nan_prob_cs", 0.0) for r in results if r])
        logger.info(
            "[LID] nan_prob(open) over %d segs: max=%.3f mean=%.3f p90=%.3f | "
            "#(nan in top3)=%d #(open>=0.3)=%d | "
            "nan_prob_cs(closed): max=%.3f mean=%.3f #(cs>=0.5)=%d #(cs>=0.35)=%d #(cs>=0.2)=%d",
            len(arr), arr.max(), arr.mean(), float(_np.percentile(arr, 90)),
            sum(1 for r in results if r and any(l in TAIWANESE_LANGS for l, _ in r["top3"])),
            int((arr >= 0.3).sum()),
            arr_cs.max(), arr_cs.mean(),
            int((arr_cs >= 0.5).sum()), int((arr_cs >= 0.35).sum()), int((arr_cs >= 0.2).sum()),
        )

    return results


def select_taiwanese(
    lid_results: List[Optional[dict]],
    min_prob: float = None,
    tw_prob_floor: float = None,
    tw_topk: int = None,
    cs_nan_prob: float = None,
) -> List[int]:
    """回傳應路由到 Breeze-26 的段落 index。

    分兩種模式：
    - **閉集模式**（LID_ALLOWED_LANGS 已設）：機率經重正規化、nan 與華語公平競爭，
      故用「重正規化後 nan 機率 ≥ cs_nan_prob」或「top-1＝台語」路由。
      （閉集下 top-k 成員判準會因類別數少而恆真，不適用。）
    - **開集模式**（停用閉集）：沿用舊三路徑 OR：top-1 min_prob / nan∈top-k / 絕對 floor。
    """
    min_prob = LID_MIN_PROB if min_prob is None else min_prob
    tw_prob_floor = LID_TW_PROB_FLOOR if tw_prob_floor is None else tw_prob_floor
    tw_topk = LID_TW_TOPK if tw_topk is None else tw_topk
    cs_nan_prob = LID_CS_NAN_PROB if cs_nan_prob is None else cs_nan_prob
    closed = bool(LID_ALLOWED_LANGS)
    out = []
    for i, r in enumerate(lid_results):
        if not r:
            continue
        if closed:
            if r.get("nan_prob_cs", 0.0) >= cs_nan_prob or r["top_lang"] in TAIWANESE_LANGS:
                out.append(i)
            continue
        if r["top_lang"] in TAIWANESE_LANGS and r["top_prob"] >= min_prob:
            out.append(i)
        elif tw_topk > 0 and any(
            lang in TAIWANESE_LANGS for lang, _ in (r.get("topk") or r.get("top3") or [])[:tw_topk]
        ):
            out.append(i)
        elif r.get("nan_prob", 0.0) >= tw_prob_floor:
            out.append(i)
    return out
