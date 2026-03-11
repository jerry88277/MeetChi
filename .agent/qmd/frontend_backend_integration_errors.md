# MeetChi 前後端串接狀態分析 (404 & 500 系統錯誤解析)

依據第一性原理與 MECE 框架，針對系統本次的服務中斷 (500 UntrustedHost 與 404 upload-url) 進行技術拆解分析：

## 一、 前端驗證防護層 (500 UntrustedHost)
*   **MECE 歸因 (認證層)：** NextAuth 框架內部有一套主機信任機制 (CSRF 防護)，在預設環境變數缺乏 `NEXTAUTH_URL` 或運行在容器部署時，會將傳入的 Request Host 視為不可信，拋出 `500 UntrustedHost` 錯誤。
*   **第一性原理修復：** 已在 `src/auth.ts` 核心設定檔中明確加入 `trustHost: true`，強制允許 Cloud Run 動態網域通過驗證。

## 二、 前端回推與後端對接層 (404 upload-url)
*   **MECE 歸因 (路由層實作遺失)：** 前端在特定操作（如新建會議時上傳現有音檔）會呼叫 `POST /api/v1/meetings/{id}/upload-url` 取得 GCS 預先簽名網址 (Presigned URL) 以進行前端直傳，將大型檔案負載卸載(offload) 離開 Python 伺服器。然而，此重要 API 端點在 FastAPI 後端中**完全遺失 (Missing Endpoint)**。這導致儘管客戶端依約定呼叫，卻立刻被框架拋回 `404 Not Found`。
*   **第一性原理修復：** 於後端 `apps/backend/app/routes/meeting_ops.py` 加入了該端點路由與對應邏輯。該端點直接整合 Google Cloud Storage Python SDK 的 `blob.generate_signed_url` 生成 60 分鐘效期的 PUT URL，並連帶更新資料庫的 `audio_url`，避免後台 Python OOM 或遇到 Timeout 限制，完成端到端架構閉環。

## 三、 部署層面 (Deployment Pipeline)
*   **修復與強制替換 Cache：** 修復完成後，透過 `gcloud builds submit` 與 `gcloud run deploy meetchi-backend --image=...` 將最新映像檔即時推上 Cloud Run，強制替換舊版服務，解決所有快取及 API 不匹配問題。藉此確保 Client 端不會因為舊圖層(Image layers) 而持續遇到 404 報錯。
