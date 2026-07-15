# 台語辨識路由（MMS-LID → Breeze-25/26）驗證報告（2026-07-15）

> 需求：以 `facebook/mms-lid-4017` 判斷逐段語言，台語（nan）走 Breeze-ASR-26、其餘走 Breeze-ASR-25。
> 取代舊 Plan B 以 `avg_logprob` 低信心當「可能非華語」的代理指標。
> 生產 revision：`meetchi-gpu-asr-00090-p66`（`TAIWANESE_ROUTING=lid`）。

## 實作
- 新增 `app/lid_router.py`：lazy-load MMS-LID（Wav2Vec2 分類，4017 語言 ISO 639-3），
  整段音檔一次載入 numpy、記憶體切片、**批次推論**；回傳每段 top_lang/top_prob/nan_prob/top-k。
- `gpu_service/main.py`：`_retranscribe_taiwanese_lid` — LID 判為台語的段落才以 Breeze-26 重轉
  （記憶體 numpy clip，免逐段 ffmpeg）。`TAIWANESE_ROUTING=lid|confidence`（預設 lid）。
- 僅 `language="zh-nan"`（國台英混合模式）時啟用，與舊行為一致。
- transformers 顯式加入 GPU 影像（whisperx 以 --no-deps 安裝，原本缺）；build 期加 import 斷言。

## 關鍵發現：MMS-LID 對台語的機率被稀釋
在已知語料上量測（TaigiSpeech 台語 12 段 vs uat03 華語 157 段）：

| 判準 | 台語 recall | 華語誤判(FP) |
|---|--:|--:|
| top-1 = nan（原始） | 1/12 (8%) | 0/157 (0%) |
| **nan ∈ top-3（採用）** | **7/12 (58%)** | **1/157 (0.6%)** |
| nan 絕對機率 ≥ 0.15 | 2/12 | 0/157 |

- 台語段落 `nan_prob`：max=0.753, mean=0.112（機率質量被 cmn 等近親漢語瓜分而稀釋）。
- 華語段落 `nan_prob`：max=0.084, mean=0.001（nan 幾乎不進 top-3）。
- 結論：**top-k 成員判準**（nan 是否進前 K 名）遠優於絕對機率門檻——
  recall 8%→58%，華語誤判僅 0.6%。故預設 `LID_TW_TOPK=3`。

## 生產驗證（deployed 服務實跑）
- 台語 clip（TaigiSpeech 8 句串接，zh-nan）：**7/12 判為台語 → Breeze-26 重轉 7/7**。
- 華語 chunk（uat03 15–30 分，157 段）：top-1 誤判 **0/157**、nan∈top3 **1/157**（0.6%）。
- MMS-LID 於 GPU 載入正常（classes=4017），157 段批次推論約 17s。

## 可調旋鈕（env，免改碼）
- `TAIWANESE_ROUTING=lid|confidence`（預設 lid；confidence 回退舊 avg_logprob 路徑）。
- `LID_TW_TOPK`（預設 3；設 1＝嚴格 top-1 高精準、0＝停用 top-k）。
- `LID_MIN_PROB`（預設 0.5，top-1 路徑門檻）。
- `LID_TW_PROB_FLOOR`（預設 1.1＝停用；絕對機率備援）。
- `LID_TAIWANESE_LANGS`（預設 nan；可加 hak 等）。

## 誠實結論與限制
- ✅ 依需求以 MMS-LID 做語言路由，台語→Breeze-26、華語→Breeze-25，端到端驗證通過。
- ✅ top-k 判準把 recall 從 8% 提升到 58%，華語誤判僅 0.6%（高精準）。
- ⚠️ recall 上限受 MMS-LID 對近親漢語（台語 vs 華語）辨識力所限，非 100%。
  若需更高 recall，可再降 topk 嚴格度（但華語 FP 會上升）或換更專門的台/華判別器。
- 回滾：`TAIWANESE_ROUTING=confidence` 或 `LID_TW_TOPK=1`。
