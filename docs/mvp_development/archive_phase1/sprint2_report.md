# Sprint 2 結案報告：不中斷轉錄與 LLM 潤飾整合

**日期**: 2025-12-09
**狀態**: 完成

## 1. 執行摘要
本 Sprint 成功達成 MVP 核心價值主張的關鍵一步：將即時轉錄 (ASR) 與後處理潤飾 (LLM) 結合。我們建立了一個獨立的 LLM 服務 (基於聯發科 Breeze2 3B 模型)，並將其無縫整合至 FastAPI 閘道中。前端介面也進行了重大重構，實現了「先顯示原始稿，再非同步更新潤飾稿」的流暢使用者體驗。雖然固定時間切分 (Fixed Chunking) 帶來的斷句問題仍存在，但系統架構已驗證可行，為後續優化奠定了堅實基礎。

## 2. 完成的功能與任務
*   **LLM 服務建置 (`apps/llm_service`)**:
    *   建立基於 Flask 的獨立微服務。
    *   成功整合 `MediaTek-Research/Llama-Breeze2-3B-Instruct` 模型。
    *   解決了 PyTorch 2.6+ 與模型加載的相容性問題 (Weights only load failed)。
    *   解決了多模態模型 (InternVL) 在純文字任務上的呼叫適配問題 (`AutoModel` vs `AutoModelForCausalLM`)。
    *   實作了 `/polish` 端點，提供低延遲 (約 1 秒) 的文字潤飾功能。
*   **後端整合 (`apps/backend`)**:
    *   升級 `app.main.py` 中的 WebSocket 處理邏輯，支援 JSON 格式訊息傳輸。
    *   實作了非同步 HTTP 用戶端 (`httpx`)，在接收 ASR 結果後併發呼叫 LLM 服務。
    *   設計了 `raw` (原始) 與 `polished` (潤飾) 兩種訊息類型，並附帶唯一 `segment_id` 以供前端對應。
    *   **關鍵修復**: 解決了 `whisperx` 在 Python 3.12 環境下的依賴衝突，透過降級/重裝 `torch`, `torchaudio`, `torchvision` 至 2.8.0+cu126 版本。
*   **前端重構 (`apps/frontend`)**:
    *   重構狀態管理，從單一字串改為 `Segment` 物件陣列 (`{id, content, isPolished}`)。
    *   實作了動態更新邏輯：收到 `polished` 訊息時，精確替換對應 ID 的原始文字。
    *   增加了系統音訊 (System Audio) 擷取功能，繞過麥克風硬體限制。
*   **參數調優**:
    *   驗證了 `BUFFER_SIZE_SECONDS` 對識別完整性的影響，最終從 2 秒調整為 5 秒，在延遲與準確度之間取得較佳平衡。

## 3. 技術挑戰與解決方案
*   **PyTorch 2.6+ 安全性限制**:
    *   **問題**: `torch.load` 預設啟用 `weights_only=True`，導致 `pyannote.audio` (VAD) 加載失敗。
    *   **解法**: 使用 `torch.serialization.add_safe_globals()` 手動將 `omegaconf`, `pyannote` 相關類別加入白名單。
*   **Python 3.12 相容性**:
    *   **問題**: `whisperx` 依賴舊版 `torch`，官方未提供 Python 3.12 的預編譯 GPU 版本。
    *   **解法**: 經過測試，成功安裝 `torch 2.8.0+cu126` 組合，滿足了依賴需求。
*   **Breeze2 3B 模型呼叫**:
    *   **問題**: 該模型為多模態架構，使用標準 `AutoModelForCausalLM` 載入會報錯。
    *   **解法**: 改用 `AutoModel` 並配合 `MRPromptV3` 及 `pixel_values=None` 參數進行純文字推論。
*   **ASR 斷句破碎**:
    *   **問題**: 2 秒緩衝區導致句子被切斷，影響 LLM 潤飾效果。
    *   **應變**: 增加緩衝區至 5 秒，雖犧牲部分即時性但顯著提升了語意完整性。

## 4. 待優化項目 (移至 Sprint 3 或 Backlog)
*   **音訊切分策略**: 目前的固定時間切分仍會切斷句子。需研究 **滑動窗口 (Overlapping)** 或 **VAD 觸發** 機制。
*   **Prompt 工程**: LLM 有時會過度改寫或包含客套話。需進一步微調 System Prompt。
*   **幻覺問題**: 當輸入文字極度破碎時，LLM 會產生幻覺。這主要依賴於 ASR 上游品質的改善。

## 5. 下一步 (Sprint 3)
*   **雙語翻譯**: 擴充 LLM 服務，增加翻譯功能。
*   **UI/UX 升級**: 實作雙語對照介面、語言切換按鈕。
*   **部署準備**: 開始規劃容器化與雲端部署 (Render/GCP)。
