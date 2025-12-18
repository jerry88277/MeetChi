# Sprint 3 結案報告：核心優化與雙語翻譯

**日期**: 2025-12-10
**狀態**: 完成

## 1. 執行摘要
本 Sprint 針對 MVP 的即時性與準確性進行了深度的架構優化與調校。我們成功引入了 **Pseudo-Streaming** 機制與 **Silero VAD**，將轉錄延遲從 15 秒以上大幅降低至 2-5 秒內。透過 **Context-Aware ASR**、**Context-Aware LLM** 與 **Few-Shot Prompting**，我們實現了高品質的即時雙語翻譯，並顯著改善了 ASR 的語意錯誤（例如成功將「程序」修正為「城市」）。同時，導入多層次的幻覺過濾機制，有效遏止了 ASR 的無意義輸出。雖然偶爾仍有 LLM 的隨機性導致的語意重複或語言混淆，但系統已具備各項核心功能，足以進入下一階段的雲端部署驗證。

## 2. 完成的功能與任務
*   **低延遲架構 (Pseudo-Streaming)**:
    *   在後端實作了 `snapshot()` 機制，允許在 VAD 切分前每 2 秒進行一次「部分轉錄 (Partial Transcription)」。
    *   前端支援 `isPartial` 狀態，以斜體灰色顯示即時更新的文字，大幅提升了使用者的即時感。
*   **抗噪 VAD 升級與優化**:
    *   將原本基於能量 (RMS) 的 VAD 替換為 **Silero VAD (DNN)**，有效區分人聲與背景音樂/噪音。
    *   加入了 RMS 雙重檢查機制 (Threshold 0.005)，過濾掉極微弱的背景人聲幻覺（如「媽媽」、「好」）。
    *   修正 Silero VAD 的輸入尺寸問題，確保模型能正確處理音訊片段。
    *   將強制切分時間 (`max_duration`) 從 15 秒逐步縮短至 5 秒，確保最差情況下的延遲也在可接受範圍內。
*   **ASR 模型與精度提升**:
    *   將 ASR 核心從 `whisperx` 切換為 **`faster-whisper`**，獲得更精細的參數控制。
    *   **Context-Aware ASR**: 透過 `initial_prompt` 將前文注入 ASR 模型，大幅改善短片段的語意準確性（例如成功將 ASR 錯誤的「程序」修正為「城市」）。
    *   **確定性與精度**: 設定 `temperature=0` 確保轉錄結果的確定性，`beam_size=5` 提升轉錄品質。
    *   **模型升級**: 使用 `large-v3` 模型，並透過 `info.no_speech_prob < 0.6` 進一步過濾噪音片段，提升 ASR 資源使用效率。
    *   **繁體引導**: 在 `initial_prompt` 中加入「以下是繁體中文的內容」，引導 ASR 輸出繁體中文，解決簡體字問題。
*   **雙語翻譯與上下文修正 (LLM)**:
    *   重構 LLM 服務，支援 `previous_context`、`source_lang` 和 `target_lang` 參數。
    *   設計了 **Context-Aware Prompt**，讓 LLM 能參考上文與語言設定，修正 ASR 錯誤。
    *   實作了 **Few-Shot Prompting**，強制 LLM 輸出 JSON 格式 (`refined`, `translated`)。
    *   **語言一致性檢查**: 在 LLM 服務層級加入正則表達式檢查。若要求中文（`source_lang='zh'`)，但 LLM 輸出大量英文，則強制回退到原始 ASR 文字，切斷語言翻轉的惡性循環。
*   **前端 UI/UX**:
    *   實作了 **雙語顯示模式** (Single/Dual) 與 **語言互換** 功能。
    *   透過 WebSocket 向後端實時發送語言配置。
    *   支援由後端驅動的狀態更新（Partial -> Raw -> Polished）。
    *   修正了前端 `audioSource` 錯誤。

## 3. 技術挑戰與解決方案
*   **延遲過高 (15s+)**:
    *   **原因**: 原本的 VAD 邏輯在背景音樂干擾下無法偵測到靜音，導致一直累積到最大緩衝區。
    *   **解法**: 引入 Silero VAD 並調降 `max_duration` 至 5 秒，配合 Pseudo-Streaming 提供中間結果。
*   **LLM 幻覺 ("謝謝你", "媽媽") 與 ASR 重複**:
    *   **原因**: Whisper 對靜音或微弱雜訊過敏，且在長時間無語音時容易重複。
    *   **解法**: 在 ASR 層級建立 `HALLUCINATIONS` 過濾清單（部分匹配）；在 VAD 層級加入 RMS 最小能量檢查；在 ASR 層利用 `no_speech_prob` 參數。
*   **前端崩潰 (Object as Child)**:
    *   **原因**: LLM 偶爾輸出嵌套 JSON 或後端未正確解析，導致將物件傳給前端渲染。
    *   **解法**: 在後端與 LLM 服務層級加入嚴格的型別檢查與 `str()` 強制轉型防禦。
*   **ASR/LLM 語言翻轉與中英夾雜**:
    *   **原因**: `whisperx` 不支援 `initial_prompt`，導致 ASR 缺乏上下文；LLM 傾向於補全或語言翻轉。
    *   **解法**: 切換至 `faster-whisper` 以支援 `initial_prompt`。LLM Prompt 加強負面約束，並在 LLM 服務層加入語言一致性檢查。
*   **WebSocket 連線錯誤**:
    *   **原因**: 客戶端斷開後，後端任務仍試圖發送訊息。
    *   **解法**: 增加 `try...except RuntimeError` 處理 WebSocket 發送和接收。

## 4. 已知限制與待辦事項
*   **LLM 偶爾仍有語意重複**: 即使 Prompt 嚴格約束，LLM 偶爾仍會因嘗試補齊語意而少量重複上下文。這可能需要更深入的 Prompt Engineering 或模型微調。
*   **JSON 格式穩定性**: LLM 偶爾會輸出缺引號的無效 JSON。目前採 Fallback 策略（顯示原文），未來可引入 `json_repair` 庫進行修復。
*   **講者分離 (Speaker Diarization)**: 目前 VAD 無法區分講者。此功能將規劃為會議後的離線處理任務，以避免拖慢即時轉錄速度。
*   **ASR 簡體字輸出**: 雖已加入繁體引導 Prompt，但 ASR 仍可能間歇性輸出簡體字。這可能需要進一步測試或考慮後處理轉換。
*   **ASR 偶發錯誤**: 儘管有 Context-Aware 和模型升級，ASR 在極端音訊條件下（如 "作弱"）仍可能出現錯誤，LLM 不一定能完全修正。

## 5. 下一步 (Sprint 4)
*   **雲端部署**: 準備 Dockerfile，將服務部署至 Render 或 GCP。
*   **GPU 資源管理**: 評估雲端環境下的 GPU 成本與效能。
*   **資料庫整合**: 將轉錄結果持久化至 Postgres 資料庫。
*   **前端優化**: 提升 Partial -> Final 之間的視覺過渡流暢度。