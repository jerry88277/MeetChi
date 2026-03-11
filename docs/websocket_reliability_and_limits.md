# MeetChi 錄音斷線與連線限制防護分析（Consult 報告）

## 1. 執行摘要 (Executive Summary)
針對「錄音時間超過 60 分鐘或中途斷線」的情況，我們對前端程式碼與過往文檔進行了系統性的第一性原理分析。

分析結果顯示：**前端確實已實作斷線防護與資料暫存機制，但架構上仍受限於 GCP Cloud Run 的連線時間長度限制（預設 15 分鐘，最大 60 分鐘）。** 前端能夠在異常斷線時自動重連並緩衝音訊，但在跨越 Cloud Run 絕對時限時，後端狀態保存（Session Continuation）將是接下來需留意的關鍵。

---

## 2. 歷史文檔與現況盤點 (MECE 框架分析)

### A. 基礎架構限制層 (GCP Cloud Run)
根據過往的對話與 `docs/integration_test_report.md` 第 112 行與第 147 行的明確記載：
> **文檔原文**：「Cloud Run 第二代支援 WebSocket，但需注意連接時間限制 (15min)」

**結論**：由於後端 ASR 串流依賴 WebSocket，Cloud Run 會在達到請求超時上限時**強制切斷** WebSocket 連線。此上限預設為 15 分鐘（可透過 GCP 配置提高至絕對上限 60 分鐘）。無論前端如何防護，到了這個時間點「一定會發生斷線」。

### B. 前端防護機制層 (Frontend Resilience)
我們徹底檢查了前端 `apps/frontend/src/hooks/useWebSocket.ts` 與 `page.tsx` 的原始碼，發現已實作以下三道防護牆以應對斷線與 60 分鐘限制：

1. **指數型退避重連 (Exponential Backoff Reconnect)**
   - **實作位置**：`useWebSocket.ts` 第 154 行起。
   - **機制**：當偵測到非正常中斷（`ev.code !== 1000` 且非主動結束），系統會啟動最高 3 次的自動重連機制。
   - **時間間隔**：以 2 秒為基數，呈指數增長（2s → 4s → 8s），避免瞬間流量衝擊後端。

2. **斷線無縫音訊緩衝 (Memory Buffering During Disconnect)**
   - **實作位置**：`useWebSocket.ts` 的 `sendOrBuffer` 方法與 `page.tsx` 的 `onaudioprocess` 事件。
   - **機制**：當 WebSocket 狀態轉為 `CONNECTING`（重連中）時，麥克風收音並不會停止。每一塊 16kHz 的 PCM 音訊碎片會被推進 `pendingChunksRef.current` 這個陣列暫存。
   - **行為**：一旦重新連線成功（`onopen` 觸發），系統會**瞬間傾印（Flush）** 所有積累的音訊資料給後端，確保語音資料「一滴不漏」。

3. **雙重備援轉錄 (Web Speech API Fallback)**
   - **實作位置**：`page.tsx` 第 540 行起。
   - **機制**：除了將語音傳給後端外，前端也同時開啟了瀏覽器內建的 Web Speech API 作為即時文字的 Backup，即使在 WebSocket 斷線的幾秒鐘內，畫面上仍可能持續顯示辨識文字，維持良好的 UX。

### C. 後端狀態延續層 (Backend Session State)
前端雖能重連並補發音訊，但每次重連對後端而言都是一個新的 WebSocket Session。
- 若後端 API 未實作 Session Continuation（將不同 WebSocket 連線認列為同一個會議 ID），則斷線重連後可能會導致重新建立語音檔，或覆蓋前次內容。

---

## 3. 顧問建議與下一步行動 (Action Items)

基於上述解析，我們已經確認**前端擁有完善的自動重連與緩衝防斷線能力**。然而整體防護仍有需強化的環節：

1. **延長 Cloud Run Request Timeout 設定 (配置層)**
   - **行動**：可利用 Terraform (`cloudrun.tf`) 或 gcloud CLI，將 Cloud Run 的 `timeoutSeconds` 明確指定至 `3600`（60分鐘），將強制斷線點延後至極限。
2. **斷線分段與接續邏輯優化 (邏輯層)**
   - **行動**：檢視後端 `FastAPI` 處理 WebSocket 連線的邏輯。確保當接收到帶有相同 `meeting_id` 的重連請求時，能夠將後續送來的 PCM 緩衝資料「接續（append）」至現有音訊檔與轉錄對話中，而非開啟新對話。
3. **極限時長處理方案 (架構層)**
   - **行動**：如果確定會議常態性超過 60 分鐘，考慮在前端實作「每 50 分鐘自動產生斷點，靜默重起新連線並關聯會議」的軟重啟機制，主動迴避 Cloud Run 的武斷性中斷。

---

本文件已同步保存至：`docs/websocket_reliability_and_limits.md` 作為未來的開發防護準則參考。
