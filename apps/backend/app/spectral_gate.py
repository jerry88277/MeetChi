"""
Pre-Whisper Spectral Gate — 幻覺抑制（訊號層）

承接 2026-07-10 研究（docs/research/uat03_hallucination_analysis/）：
會議「開頭」的多人交談/會前閒聊屬遠場、悶、低頻主導的 murmur——音量與真實語音
相同（RMS d=0.02，故 audio_stats 判「健康」）、非白噪（flatness 較低=較 tonal），
但缺高頻 articulation（子音/formant）。Whisper 被迫把這種「像語音的非語音」強解成
連鎖幻覺。

驗證結論（前 12 分鐘，7:52 為真值邊界）：判別在**頻譜形狀＋結構**而非音量。
最強單一特徵 A1 頻譜傾斜（2–4kHz / <750Hz, dB）d=2.39/90%；A1+B1（低頻 CPP）
多變量 d=2.54/92%，決策邊界落在 7:52。

本模組把該 Gate 落地為 **pre-Whisper 遮罩（mask-not-delete）**：
  score = robust_z(spectral_tilt) + robust_z(low_band_CPP)
每場以 median/MAD 自適應正規化（抗房間/麥克風漂移）。**預設 full 模式**：全檔遲滯
掃描，把持續「低分且悶（絕對高頻占比低）」的區段遮成靜音，時間軸不變，交由
faster-whisper 的 VAD 自然跳過。real-audio 驗證（uat03 前 12 分，7:52 為幻覺邊界）：
full 模式遮 40.6%，幾乎全落在 2.5–463.5s 幻覺區內，真實語音區（472s+）僅誤遮一個
2s——**絕對高頻護欄**有效保護真實語音。另備 leading 模式（只遮開頭領先低分區），
但實測會被錄音起始的高頻瞬態誤判 onset 而失效，故不設為預設。遮罩＝將該區樣本歸零。

純 numpy.fft（community-1 GPU 環境無 scipy）。
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

SR = 16000  # gate 僅在 16kHz mono 上運作（whisperx.load_audio 的輸出）


# ============================================
# 參數（env 可覆寫，利於 A/B 調校）
# ============================================

@dataclass
class GateConfig:
    win_s: float = field(default_factory=lambda: float(os.getenv("SGATE_WIN_S", "1.5")))
    hop_s: float = field(default_factory=lambda: float(os.getenv("SGATE_HOP_S", "0.5")))
    # 模式：full（全檔遲滯，實測對真實會議最穩且準，預設）｜ leading（只遮開頭領先低分區）
    # 實測（uat03 前12分，7:52 為幻覺邊界）：full 遮 40.6%，幾乎全落在 2.5–463.5s
    # 幻覺區內，真實語音區（472s+）僅誤遮一個 2s，絕對高頻護欄有效保護真實語音。
    # leading 模式會被開頭高頻瞬態（錄音起始 click）誤判 onset=0 而失效，故不設為預設。
    mode: str = field(default_factory=lambda: os.getenv("SGATE_MODE", "full").lower())
    # robust-z 門檻（單位為 MAD-z）：低於 enter → 幻覺傾向；高於 exit → 真實傾向
    enter_z: float = field(default_factory=lambda: float(os.getenv("SGATE_ENTER_Z", "-0.4")))
    exit_z: float = field(default_factory=lambda: float(os.getenv("SGATE_EXIT_Z", "0.3")))
    # 判定「真實語音已開始」需持續的秒數（leading 模式用）
    min_real_s: float = field(default_factory=lambda: float(os.getenv("SGATE_MIN_REAL_S", "2.0")))
    # 一段遮罩最短持續（避免打小洞）
    min_gate_s: float = field(default_factory=lambda: float(os.getenv("SGATE_MIN_GATE_S", "2.0")))
    # 護欄：單一 chunk 最多遮罩比例，超過視為疑似誤判/整段皆壞，仍套用但強制 warn
    max_gate_frac: float = field(default_factory=lambda: float(os.getenv("SGATE_MAX_GATE_FRAC", "0.85")))
    # 絕對 articulation 下限：高頻(2–4kHz)能量占比高於此者，無論自適應分數如何都**不**遮
    # （防止在「整段皆真實」的 chunk 誤刪清晰語音）
    abs_hf_ratio_keep: float = field(default_factory=lambda: float(os.getenv("SGATE_ABS_HF_KEEP", "0.06")))


# ============================================
# 逐窗特徵（純 numpy.fft）
# ============================================

def _frame_features(audio: np.ndarray, sr: int, win_s: float, hop_s: float):
    """回傳 (times, tilt_db, cpp, hf_ratio)，每 hop 一格。"""
    n = int(round(win_s * sr))
    hop = int(round(hop_s * sr))
    if n <= 0 or hop <= 0 or len(audio) < n:
        return (np.array([]), np.array([]), np.array([]), np.array([]))

    window = np.hanning(n).astype(np.float32)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    low_mask = freqs < 750.0
    high_mask = (freqs >= 2000.0) & (freqs < 4000.0)
    eps = 1e-10

    # 倒頻譜 F0 搜尋範圍 60–400 Hz → quefrency 索引
    q = np.arange(n) / sr
    q_lo, q_hi = 1.0 / 400.0, 1.0 / 60.0
    ceps_idx = np.where((q >= q_lo) & (q <= q_hi))[0]

    times, tilt_db, cpp, hf_ratio = [], [], [], []
    for start in range(0, len(audio) - n + 1, hop):
        frame = audio[start:start + n] * window
        spec = np.fft.rfft(frame)
        power = (spec.real ** 2 + spec.imag ** 2) + eps

        low_e = float(power[low_mask].sum())
        high_e = float(power[high_mask].sum())
        total_e = float(power.sum())

        tilt_db.append(10.0 * np.log10((high_e + eps) / (low_e + eps)))
        hf_ratio.append(high_e / (total_e + eps))

        # CPP：log-power 倒頻譜峰值相對回歸基線的突起量
        if len(ceps_idx) >= 3:
            logp = np.log(power)
            ceps = np.fft.irfft(logp, n=n)
            region = ceps[ceps_idx]
            peak_local = int(region.argmax())
            peak_val = float(region[peak_local])
            a, b = np.polyfit(q[ceps_idx], region, 1)
            baseline = a * q[ceps_idx][peak_local] + b
            cpp.append(peak_val - baseline)
        else:
            cpp.append(0.0)

        times.append(start / sr)

    return (np.asarray(times), np.asarray(tilt_db), np.asarray(cpp), np.asarray(hf_ratio))


def _robust_z(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    scale = 1.4826 * mad + 1e-9
    return (x - med) / scale


# ============================================
# Gate 決策
# ============================================

@dataclass
class GateResult:
    spans: List[Tuple[float, float]]  # 要遮罩（靜音）的 (start_s, end_s)
    gated_frac: float
    n_windows: int
    mode: str
    real_onset_s: Optional[float]
    diagnostics: dict


def compute_gate(audio: np.ndarray, sr: int = SR, cfg: Optional[GateConfig] = None) -> GateResult:
    cfg = cfg or GateConfig()
    times, tilt, cpp, hf = _frame_features(audio, sr, cfg.win_s, cfg.hop_s)
    dur = len(audio) / sr if sr else 0.0

    if times.size == 0:
        return GateResult([], 0.0, 0, cfg.mode, None, {"reason": "too_short"})

    score = _robust_z(tilt) + _robust_z(cpp)
    step = cfg.hop_s

    # 每窗「可遮」條件：分數低（自適應）且高頻占比低（絕對護欄）
    is_low = (score < cfg.enter_z) & (hf < cfg.abs_hf_ratio_keep)
    is_high = score > cfg.exit_z
    # 「非悶」= 明顯真實傾向：分數高 或 高頻占比足夠（絕對）
    not_muffled = is_high | (hf >= cfg.abs_hf_ratio_keep)

    spans: List[Tuple[float, float]] = []
    real_onset: Optional[float] = None

    if cfg.mode == "leading":
        # 找「真實語音起點」：首個持續 min_real_s 的 not_muffled run
        need = max(1, int(round(cfg.min_real_s / step)))
        run = 0
        onset_idx = None
        for i in range(len(score)):
            run = run + 1 if not_muffled[i] else 0
            if run >= need:
                onset_idx = i - need + 1
                break
        if onset_idx is None:
            # 整段未見持續真實語音 → 仍只遮「持續低分且悶」的區段（絕不盲遮），封頂
            real_onset = None
            spans = _mask_to_spans(is_low, times, step, cfg.min_gate_s, dur)
        else:
            real_onset = float(times[onset_idx])
            # 領先區 [0, real_onset) 內，只遮「持續低分且悶」的部分
            lead_mask = is_low[:onset_idx]
            spans = _mask_to_spans(lead_mask, times[:onset_idx], step, cfg.min_gate_s, real_onset)
    else:  # full 模式：遲滯掃全檔
        spans = _hysteresis_spans(is_low, is_high, times, step, cfg.min_gate_s, dur)

    # 護欄：總遮罩比例
    gated = sum(e - s for s, e in spans)
    frac = gated / dur if dur else 0.0
    if frac > cfg.max_gate_frac:
        logger.warning(
            "[SpectralGate] gated_frac=%.2f > cap=%.2f — 疑似誤判/整段皆壞，"
            "截斷至上限以保安全", frac, cfg.max_gate_frac
        )
        spans = _truncate_to_cap(spans, dur * cfg.max_gate_frac)
        gated = sum(e - s for s, e in spans)
        frac = gated / dur if dur else 0.0

    diag = {
        "score_min": float(score.min()), "score_max": float(score.max()),
        "score_median": float(np.median(score)),
        "tilt_median": float(np.median(tilt)), "cpp_median": float(np.median(cpp)),
        "hf_median": float(np.median(hf)),
    }
    return GateResult(spans, frac, len(score), cfg.mode, real_onset, diag)


def _mask_to_spans(mask: np.ndarray, times: np.ndarray, step: float,
                   min_gate_s: float, hard_end: float) -> List[Tuple[float, float]]:
    """連續 True 段 → spans，濾掉短於 min_gate_s 的。"""
    spans: List[Tuple[float, float]] = []
    i = 0
    ntot = len(mask)
    while i < ntot:
        if mask[i]:
            j = i
            while j < ntot and mask[j]:
                j += 1
            s = float(times[i])
            e = float(times[j - 1]) + step
            e = min(e, hard_end)
            if e - s >= min_gate_s:
                spans.append((s, e))
            i = j
        else:
            i += 1
    return spans


def _hysteresis_spans(is_low, is_high, times, step, min_gate_s, dur):
    spans: List[Tuple[float, float]] = []
    in_gate = False
    gs = 0.0
    for i in range(len(is_low)):
        t = float(times[i])
        if not in_gate and is_low[i]:
            in_gate = True
            gs = t
        elif in_gate and is_high[i]:
            in_gate = False
            ge = t
            if ge - gs >= min_gate_s:
                spans.append((gs, ge))
    if in_gate:
        ge = min(dur, float(times[-1]) + step)
        if ge - gs >= min_gate_s:
            spans.append((gs, ge))
    return spans


def _truncate_to_cap(spans, cap_seconds):
    out, acc = [], 0.0
    for s, e in spans:
        if acc >= cap_seconds:
            break
        length = e - s
        if acc + length <= cap_seconds:
            out.append((s, e))
            acc += length
        else:
            out.append((s, s + (cap_seconds - acc)))
            acc = cap_seconds
    return out


# ============================================
# 套用（mask-not-delete）
# ============================================

def apply_gate(audio: np.ndarray, sr: int = SR,
               cfg: Optional[GateConfig] = None) -> Tuple[np.ndarray, GateResult]:
    """回傳 (masked_audio, GateResult)。masked_audio 為 audio 的複本，遮罩區歸零。"""
    cfg = cfg or GateConfig()
    res = compute_gate(audio, sr, cfg)
    if not res.spans:
        return audio, res
    out = audio.copy()
    for s, e in res.spans:
        i0 = max(0, int(round(s * sr)))
        i1 = min(len(out), int(round(e * sr)))
        if i1 > i0:
            out[i0:i1] = 0.0
    logger.info(
        "[SpectralGate] mode=%s gated_frac=%.2f real_onset=%s spans=%d %s",
        res.mode, res.gated_frac,
        f"{res.real_onset_s:.1f}s" if res.real_onset_s is not None else "None",
        len(res.spans),
        [(round(s, 1), round(e, 1)) for s, e in res.spans[:6]],
    )
    return out, res
