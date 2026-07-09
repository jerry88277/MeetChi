# uat03 會議前 8 分鐘幻覺區 — 音訊訊號分析報告

會議：`50df45ce`（uat03），已知前 8 分鐘為 Whisper 幻覺。
分析音訊：前 12 分鐘（16kHz mono），逐 2 秒窗、1 秒 hop。

## 第一性原理
Whisper 幻覺 = 對「類語音的非語音訊號」被迫解碼。要找的是**幻覺區 vs 真實語音區在訊號維度上的可分離特徵**，作為進 Whisper 前的 gate。

## 判別力結果（Cohen's d，幻覺區 0-8min vs 真實區 8min+）

| 排名 | 特徵 | d | 幻覺區 | 真實區 | 判讀 |
|---|---|---|---|---|---|
| 1 | Zero-Crossing Rate | **1.97** | 0.084 | 0.136 | 幻覺區低 → 缺高頻 |
| 2 | Spectral Centroid | **1.92** | 1320Hz | 1860Hz | 幻覺區頻譜重心低 |
| 3 | 語音頻帶能量占比(100-2kHz) | **1.59** | 0.78 | 0.66 | 幻覺區能量擠在低頻 |
| 4 | Spectral Flatness | **1.41** | 0.36 | 0.49 | 幻覺區**更tonal**(非白噪) |
| 5 | Spectral Rolloff 85% | **1.38** | 2800Hz | 3760Hz | 幻覺區高頻少 |
| 6 | 短時RMS變異 | 0.83 | 5.1dB | 7.4dB | 幻覺區更單調穩態 |
| 7 | 基頻週期性 | 0.43 | - | - | 弱 |
| 8 | Voiced Ratio | 0.36 | - | - | 弱 |
| 9 | **RMS 響度** | **0.03** | -22.4dBFS | -22.1dBFS | **無差異！非音量問題** |

## 核心洞見（MECE）
幻覺區**不是靜音**（響度相同 -22dBFS，故 audio_stats 判 healthy）、**也不是白噪**（flatness 較低=較 tonal）。它是**低頻主導、悶糊、穩態、單調**的訊號——典型的：
- 遠場/隔空收音的會前交談（麥克風離人遠）
- 冷氣/環境嗡聲 + 低頻殘響
- 裝置播放聲外漏

→ 有足夠能量不被判靜音，卻缺乏近場清晰語音的**高頻 articulation（子音/共振峰）** → Whisper 硬解成幻覺。

## 綜合語音可信度 gate（可落地）
用最強 3 特徵 `z(centroid)+z(rolloff)+z(ZCR)` 合成分數：
- **幻覺區 74% 低於門檻**、**真實區 96% 高於門檻** → 單一輕量特徵即可有效區分。

## 進 Whisper 前的處理建議（MECE，由簡到強）
1. **頻譜 gate（最輕量、CP值最高）**：逐窗算 centroid/rolloff/ZCR 合成分數，低於門檻的區段**不餵給 Whisper**（標記非語音）。純 numpy/scipy、無需模型。
2. **Silero VAD 取代能量 VAD**：現用 faster-whisper 內建 VAD 對「低頻悶糊murmur」判別力不足；Silero 是學習式語音存在偵測，對此類遠場語音更準。
3. **高通濾波 + articulation 檢查**：幻覺區缺 >2kHz 能量，可對「高頻能量占比過低」的段落直接跳過或降權。
4. **與已部署的幻覺抑制參數疊加**：condition_on_previous_text=False + compression/logprob/no_speech 門檻（已上線 gpu 00081-h7d）。

## 產出圖檔
- `uat03_signal_features.png` — 9 維特徵逐分鐘時序（標註 8:00 分界）
- `uat03_spectrogram.png` — 頻譜圖（左低頻悶糊 vs 右高頻清晰）
- `uat03_speech_confidence.png` — 綜合語音可信度分數 + 建議門檻
