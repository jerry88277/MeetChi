# 語音轉錄模型調研報告 (2025-2026)

> 建立日期: 2026-06-10  
> 目的: 調研 MeetChi GPU ASR 服務的模型升級選項  
> 現行模型: OpenAI Whisper Large V3 (自建 GPU 推理)

---

## 一、市場全景總覽

### 2026 年度 ASR 模型 WER 排行（FLEURS 25 語言基準）

| 排名 | 模型 | 開發商 | 平均 WER | 開源 | 部署方式 |
|------|------|--------|---------|------|---------|
| 1 | ElevenLabs Scribe v2 | ElevenLabs | 2.3% | ❌ API | 雲端 API |
| 2 | MAI-Transcribe-1 | Microsoft | 3.8% | ❌ Azure | Azure Foundry |
| 3 | GPT-4o-transcribe | OpenAI | ~4.0% | ❌ API | OpenAI API |
| 4 | NVIDIA Canary-Qwen 2.5B | NVIDIA | 5.6% | ✅ CC-BY-4.0 | 自建 GPU |
| 5 | IBM Granite Speech 3.3 | IBM | 5.8% | ✅ | 自建 GPU |
| 6 | Whisper Large V3 | OpenAI | 7.4% | ✅ MIT | 自建 GPU |
| 7 | Whisper Large V3 Turbo | OpenAI | 7.75% | ✅ MIT | 自建 GPU |
| 8 | Breeze ASR 25 | MediaTek Research | — | ✅ Apache 2.0 | 自建 GPU |

---

## 二、OpenAI 系列

### 2.1 Whisper 家族（開源自建）

| 模型 | 參數量 | WER | VRAM | 推理速度（L4 GPU） | 備註 |
|------|--------|-----|------|-------------------|------|
| Whisper Large V3 | 1.55B | 7.4% | ~6GB | 15x realtime | **MeetChi 現用** |
| Whisper Large V3 Turbo | 809M | 7.75% | ~3.5GB | 30x realtime | 速度翻倍，精度略降 |
| Distil-Whisper Large V3 | ~756M | ~8.0% | ~3GB | 25x realtime | 蒸餾版，較小 |

**重點**: OpenAI 至今（2026/06）**未發布 Whisper V4**。所有標題含「Whisper V4」的文章均為 SEO 誤導。

### 2.2 GPT-4o 系列轉錄模型（API 付費）

| 模型 | WER | 價格 | 特色 |
|------|-----|------|------|
| GPT-4o-transcribe | ~3.5% | $0.36/hr ($6/1000min) | 最高精度 |
| GPT-4o-mini-transcribe | ~4.0% | $0.18/hr ($3/1000min) | 性價比最高 |

### 2.3 GPT-Realtime 系列（2026/05 新發布）

來源: [TechNews 報導](https://technews.tw/2026/05/08/openai-introduces-three-audio-models-in-the-api/)

| 模型 | 用途 | 價格 | 特色 |
|------|------|------|------|
| GPT-Realtime-2 | 即時語音互動 | $32/M input tokens | GPT-5 級推理能力 |
| GPT-Realtime-Translate | 即時翻譯 | $0.034/min | 70→13 種語言 |
| **GPT-Realtime-Whisper** | **串流語音轉文字** | **$0.017/min ($1.02/hr)** | 即時轉錄，低延遲 |

**MeetChi 適用性分析**:
- GPT-Realtime-Whisper 適合即時轉錄場景（如會議進行中的字幕）
- 但以批次轉錄（會後上傳錄音）來說，GPT-4o-mini-transcribe ($0.18/hr) 更經濟
- **隱私疑慮**: 企業會議內容送至 OpenAI API，需評估合規性

---

## 三、Microsoft 系列

### 3.1 MAI-Transcribe-1（2026/04 發布）

| 指標 | 數據 |
|------|------|
| 平均 WER | 3.8%（FLEURS 25 語言） |
| 推理速度 | 69x realtime（業界最快） |
| 支援語言 | 25 語言（含中文、日文、韓文） |
| 部署 | Azure Foundry API |
| 定價 | $6/1000 分鐘 = $0.36/hr |
| 開源 | ❌（僅 API） |
| Diarization | 規劃中（尚未支援） |

**優勢**: WER 最低 + 速度最快，且奇美已使用 Azure/Entra ID 生態系
**劣勢**: 非開源、需送資料至雲端、尚無 speaker diarization

### 3.2 Azure Speech Service（既有服務）

- 支援 Real-time + Batch transcription
- Custom Speech 可微調（企業專有詞彙）
- 與 MeetChi 的 Entra ID 認證無縫整合
- 定價: ~$1/hr (Standard), Custom model 額外費用

---

## 四、MediaTek Research Breeze 系列（台灣在地化）

### 4.1 Breeze ASR 25（2025/07 發布）

| 指標 | 數據 |
|------|------|
| 基礎架構 | Fine-tuned Whisper Large V2 |
| 專注語言 | 台灣華語 + 中英 code-switching |
| 訓練數據 | ~10,000 小時合成華語 + 1,738 小時英語 |
| WER 改善 | CommonVoice-zh-TW: -19%, CSZS code-switch: -56% |
| 授權 | Apache 2.0（完全開源） |
| 量化支援 | ✅ int8_float16（可在 RTX 3050 4GB VRAM 推理） |

**MeetChi 高度適用**: 
- 專為台灣口音優化，MeetChi 用戶均為台灣企業員工
- 中英夾雜場景（會議中常用英文術語）效果大幅提升
- 量化版可在現有 L4 上跑更多 concurrent streams

### 4.2 Breeze ASR 26（2026 發布）

| 指標 | 數據 |
|------|------|
| 專注語言 | 台灣閩南語（Taigi / 台語） |
| 訓練數據 | ~10,000 小時合成台語語音 |
| 輸出格式 | 華語漢字轉寫 |
| 平均 CER | 30.13% |
| 授權 | 開源 |

**適用性**: 若 MeetChi 需支援台語會議，可作為備選

---

## 五、NVIDIA 系列

### 5.1 Canary-1B-v2（2025/08 發布）

| 指標 | 數據 |
|------|------|
| 參數量 | ~1B |
| 架構 | FastConformer + Transformer Decoder |
| 語言 | 25 歐洲語言 + 英語 |
| WER | 5.6%（最佳英語模型） |
| 推理速度 | 比同類快 10x |
| 授權 | CC-BY-4.0 |

### 5.2 Parakeet-TDT-0.6B-v3

| 指標 | 數據 |
|------|------|
| 參數量 | 600M |
| 特色 | Streaming, 低延遲, word-level timestamps |
| 語言 | 25 語言 |
| 授權 | CC-BY-4.0 |

**適用性**: Canary/Parakeet 主攻歐洲語言，對台灣華語支援不如 Breeze ASR 25

---

## 六、推理加速方案

### 6.1 faster-whisper（CTranslate2 後端）

| 指標 | 數據 |
|------|------|
| 相對速度 | 比原版 Whisper 快 4-8x |
| VRAM 節省 | int8 量化僅需 ~3GB |
| 精度損失 | 幾乎無（< 0.1% WER 差異） |
| GitHub | github.com/SYSTRAN/faster-whisper |

### 6.2 insanely-fast-whisper（BetterTransformer/FlashAttention）

| 指標 | 數據 |
|------|------|
| 適用場景 | 大批次 GPU 吞吐量最大化 |
| 相對速度 | 比 faster-whisper 再快 20-50%（大 batch） |
| 要求 | 現代 GPU（A100/H100/Ada 最佳） |

### 6.3 比較總覽

| Runtime | 引擎 | 相對速度 | VRAM | 適用場景 |
|---------|------|---------|------|---------|
| 原版 Whisper | PyTorch | 1x | 高 | 開發/實驗 |
| Distil-Whisper | PyTorch (蒸餾) | 2x | 低 | 邊緣裝置 |
| **faster-whisper** | CTranslate2 | **4-8x** | **最低** | **⭐ 生產環境首選** |
| insanely-fast-whisper | FlashAttn | 5-10x | 中 | 大批次吞吐 |

---

## 七、MeetChi 升級建議

### 短期方案（1-2 週內可實施）

| 優先級 | 方案 | 預期效果 | 風險 |
|--------|------|---------|------|
| ⭐⭐⭐ | 切換至 **faster-whisper** 推理引擎 | 推理速度 4-8x，VRAM 降 50% → concurrency 可達 8-10 | 低（模型不變） |
| ⭐⭐⭐ | 替換為 **Breeze ASR 25** | 台灣華語 WER -19%，code-switch -56% | 低（架構相容 Whisper） |
| ⭐⭐ | 使用 **Whisper Large V3 Turbo** | 速度 2x，精度略降 0.35% | 極低 |

### 中期方案（1-2 個月）

| 優先級 | 方案 | 預期效果 | 風險 |
|--------|------|---------|------|
| ⭐⭐ | 評估 **MAI-Transcribe-1** (Azure API) | WER 降至 3.8%，69x realtime | 資料送雲端（合規審查） |
| ⭐⭐ | 評估 **GPT-4o-mini-transcribe** | WER ~4.0%，$0.18/hr | 隱私、OpenAI 依賴 |
| ⭐ | 混合架構：本地 Breeze + API fallback | 兼顧隱私與精度 | 架構複雜度增加 |

### 長期願景

| 方案 | 效果 | 時程 |
|------|------|------|
| Breeze ASR 25 + faster-whisper + int8 量化 | 15-20 concurrent streams on 1×L4 | 2-3 週 |
| 加入 speaker diarization (pyannote) | 自動辨識講者 | 1 個月 |
| 即時轉錄（GPT-Realtime-Whisper） | 會議中即時字幕 | 需另建串流架構 |

---

## 八、成本比較（處理 100 小時音源/月）

| 方案 | 月成本 | WER | 隱私 | 備註 |
|------|--------|-----|------|------|
| **現行: Whisper V3 on L4 (minScale=1)** | **~$720** | 7.4% | ✅ 完全私有 | 24/7 GPU 常駐 |
| Whisper V3 on L4 (minScale=0) | ~$200-400 | 7.4% | ✅ | 有 cold start |
| **Breeze ASR 25 on L4** | **~$720** | **~6.0%** | ✅ 完全私有 | **推薦** |
| GPT-4o-mini-transcribe (API) | $18 | ~4.0% | ⚠️ 送 OpenAI | 最便宜 |
| MAI-Transcribe-1 (Azure) | $36 | 3.8% | ⚠️ 送 Azure | 企業方案 |
| GPT-Realtime-Whisper (即時) | $102 | — | ⚠️ 送 OpenAI | 即時場景 |

---

## 九、結論與建議

### 🏆 最佳短期升級路徑
**Breeze ASR 25 + faster-whisper 引擎**
- 台灣華語精度提升 19-56%
- 推理速度提升 4-8x
- 維持完全私有（不送雲端）
- 現有 L4 GPU 硬體完全相容
- 預估可將 concurrency 從 5 提升至 8-10

### 🔄 模型熱替換可行性
Breeze ASR 25 基於 Whisper Large V2 微調，與現有 GPU ASR 服務架構相容：
1. 下載 Breeze ASR 25 模型權重
2. 替換 model path 環境變數
3. 切換推理引擎至 faster-whisper
4. 部署測試 → 切換

---

## 參考連結

- [OpenAI Whisper GitHub](https://github.com/openai/whisper)
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper)
- [Breeze ASR 25 (HuggingFace)](https://huggingface.co/MediaTek-Research/Breeze-ASR-25)
- [Breeze ASR 26 (HuggingFace)](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)
- [MAI-Transcribe-1 (Microsoft)](https://microsoft.ai/news/state-of-the-art-speech-recognition-with-mai-transcribe-1/)
- [NVIDIA Canary-1B-v2](https://huggingface.co/NVIDIA)
- [OpenAI GPT-Realtime 新語音模型 (TechNews)](https://technews.tw/2026/05/08/openai-introduces-three-audio-models-in-the-api/)
- [OpenAI Transcribe API](https://developers.openai.com/api/docs/models/gpt-4o-transcribe)
- [2026 開源 STT 模型比較](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
