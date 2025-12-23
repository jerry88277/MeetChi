# 架構差距分析報告：現有實作 vs. 研究建議

**日期**: 2025-12-22
**版本**: 1.1

## 1. 執行摘要

本報告旨在對比 **TranscriptHub MVP 目前的實作狀態** 與先前兩份深度研究報告（**ONNX 降噪整合** 與 **聲學前端優化**）中的建議架構，識別關鍵差距，並為下一階段的開發提供具體的收斂路徑。

目前 MVP 已成功建立了基於 **Tauri + Rust + cpal** 的音訊採集基礎建設，並整合了 **WebRTC VAD** 進行語音活動偵測。這是一個穩健的起點，但距離「商業級降噪」的目標仍有顯著差距。

## 2. 現狀盤點 (Current Implementation Status)

*   **前端框架**: Tauri v2 + Next.js (SSG)。
*   **視窗管理**: 實現了透明 Overlay 與獨立 Settings 視窗，解決了 Windows 邊框與拖曳問題。
*   **音訊採集 (Rust Backend)**:
    *   使用 `cpal` crate。
    *   支援麥克風與系統音訊 (Loopback)。
    *   實作了簡單的重採樣 (Resampling) 邏輯 (Naive Decimation) 以適配 16kHz 需求。
*   **VAD (語音活動偵測)**:
    *   採用 **WebRTC VAD** (`webrtc-vad` crate)。
    *   運行在獨立的音訊執行緒中。
    *   將 0.0-0.1 的浮點數閾值映射為 WebRTC 的 0-3 模式。
    *   **職責**：**作為用戶端的第一道過濾，主要目標是減少無語音的音訊數據傳輸至後端，以節省頻寬和後端處理資源。**
*   **降噪 (Noise Suppression)**: **目前尚未實作**。

## 3. 差距識別 (Gap Analysis)

基於 **MECE (相互獨立、完全窮盡)** 原則，我們從三個維度分析差距：

### 3.1 核心算法差距 (Algorithm Gap)

| 功能模組 | 研究建議 (Ideal State) | 目前實作 (Current State) | 差距評估 (Impact) |
| :--- | :--- | :--- | :--- |
| **前端 VAD** | **Silero VAD** (ONNX)<br>- 抗噪性強，高準確率<br>- 職責：**用戶端預過濾，減少傳輸** | **WebRTC VAD** (C-binding)<br>- 抗噪性弱，準確率中等<br>- 職責：**用戶端預過濾，減少傳輸** | **中**：WebRTC VAD 在安靜環境下夠用，但在嘈雜環境下容易誤判。其編譯穩定性是優勢。 |
| **後端 VAD** | **Silero VAD** 或 ASR 內建<br>- 職責：**語句切分 (Segmentation) 與時間戳校準** | **後端現有 VAD** (Pyannote 或 Energy VAD)<br>- 職責：**語句切分 (Segmentation)** | **無明顯差距**：前端 VAD 與後端 VAD 職責不同，前者為預過濾，後者為切分。兩者互補。 |
| **降噪** | **DeepFilterNet** (SOTA) 或 **nnnoiseless** (輕量)<br>- 能去除鍵盤聲、風扇聲 | **無 (None)**<br>- 僅做靜音過濾 | **高**：這是產品「降噪」賣點的核心缺失。目前僅能「切斷」靜音，無法「淨化」語音。 |
| **重採樣** | **Rubato** (Async Resampler)<br>- 高品質抗混疊濾波 | **Naive Decimation** (簡單抽樣)<br>- 每 N 個點取 1 個 | **低/中**：簡單抽樣會引入混疊 (Aliasing) 雜訊，但在語音識別場景下，對 16kHz 的影響可能尚可接受。 |

### 3.2 架構設計差距 (Architecture Gap)

| 架構層面 | 研究建議 | 目前實作 | 風險評估 |
| :--- | :--- | :--- | :--- |
| **執行緒模型** | **三執行緒管線** (Input -> Process -> Output)<br>- 利用 Ring Buffer 解耦 | **雙執行緒** (Main + Audio Thread)<br>- 音訊採集與 VAD 處理在同一執行緒 | **中**：WebRTC VAD 極快，目前不會阻塞。但若加入重型降噪模型 (DeepFilterNet)，目前的單執行緒模型將導致爆音 (Xrun)。 |
| **模型推論** | **ONNX Runtime** (ort)<br>- 統一的跨平台推理引擎 | **Native Rust/C** (webrtc-vad)<br>- 無需 ONNX Runtime | **正面差距**：目前的實作避開了 `ort` 的編譯地獄 (Dependency Hell)，對於 MVP 來說反而是更優的工程決策。 |

## 4. 收斂建議與路線圖 (Convergence Strategy)

考慮到我們在 Sprint 4.8 中遭遇的 `ort` 編譯困難，以及 MVP 對穩定性的要求，我們提出修正後的路線圖：

### Phase 1: MVP 完善 (當前階段)
*   **保持 WebRTC VAD**：不要急於切換到 Silero。WebRTC VAD 的低延遲與零依賴是目前最大的優勢。
*   **引入輕量級降噪**：**強烈建議引入 `nnnoiseless`**。
    *   **理由**：它是 RNNoise 的純 Rust 移植，**不需要 ONNX Runtime**，完全避開了我們遭遇的編譯問題。
    *   **效果**：雖不如 DeepFilterNet，但能顯著去除穩態噪音（冷氣、風扇），對使用者體驗提升巨大。
    *   **實作**：將 `nnnoiseless` crate 加入 `Cargo.toml`，並在 `audio_processor.rs` 的 VAD 判斷為 `true` 後，對音訊進行處理。

### Phase 2: 架構升級 (Next Sprint)
*   **升級重採樣**：引入 `rubato` crate 取代目前的 Naive Decimation，提升音質。
*   **gRPC 串流**：完成與後端的對接，這是功能的最後一哩路。

### Phase 3: 追求極致 (Future)
*   **再次挑戰 ONNX**：當需要在邊緣端執行 DeepFilterNet 這種 SOTA 模型時，再回頭解決 `ort` 的整合問題。屆時可以考慮將模型封裝為獨立的 Sidecar 執行檔（Python/C++），透過 stdin/stdout 通訊，徹底避開 Rust 的編譯連結問題。

## 5. 結論

目前的實作方向是**務實且正確的**。雖然與研究報告中的「全 ONNX 架構」有落差，但這是在工程現實（編譯穩定性、開發速度）下的最佳權衡。

**下一步行動建議**：
在 gRPC 整合之前，優先將 **`nnnoiseless`** 整合進目前的音訊管線。這將以最小的工程成本，填補「降噪」功能的空白。