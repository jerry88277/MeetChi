# ASR 低音量／噪音壓力測試（端到端，對 Cloud Run 生產環境）

驗證 MeetChi 生產離線 ASR（`Breeze-ASR-25` + Silero VAD）對**低音量**與**噪音**的穩健度。
完整背景與結論見 `docs/devlog/2026-07-03.md`。

## 檔案
- `e2e_cloudrun.py` — 端到端測試：對正式 Cloud Run backend 逐筆 建立會議→上傳→enqueue→輪詢→取回轉錄，算 CER。
- `validate.py` — 本機 VAD 單元驗證（import 真實 `app/vad.py`，gain/SNR sweep）。**注意**：本機無 torch → 走 Energy-VAD fallback，非生產路徑。
- `samples_meta.json` — 使用的 3 筆 ASCEND 測試樣本（純中／純英／中英混）中繼資料。
- `e2e_results.json` — 2026-07-03 生產實測結果（12 條件）。

## 樣本來源
ASCEND（HuggingFace `CAiRE/ASCEND`，CC-BY-SA 4.0）test split，挑 3 筆代表樣本。
音檔本身（parquet／wav artifacts，>100MB）**不入庫**，需重跑時依 `samples_meta.json` 的
`id` 從 ASCEND parquet 還原，或見 devlog 的下載方法。

## 重跑
```bash
python3 e2e_cloudrun.py              # 跑全部 12 條件（需 artifacts/*.wav）
python3 e2e_cloudrun.py ZH_1_original  # 單筆
```
測試會建立 `[STRESS]` 前綴的會議；跑完請 soft-delete 清理（見 devlog）。

## 關鍵結論（2026-07-03）
生產離線 ASR 對 **-40dB（≈-50dBFS）低音量穩健、不丟棄**（Whisper 內部 mel 正規化 + Silero VAD）。
本機 Energy-VAD fallback 才會丟低音量 → 不代表生產行為。真正的空轉錄成因需查個別音檔特徵
（真靜音／削波／單聲道異常），非等比衰減。
