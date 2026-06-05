# MeetChi 開發日誌：Microsoft OAuth SSO 整合 + Google OAuth 修復

> 建立日期：2026-06-02  
> 作者：jerry_tai  
> 相關 PR / Branch：—（直接 commit 至 main，待 Azure AD 資源到位後補齊測試）

---

## 一、緊急修復：Google OAuth `redirect_uri_mismatch`（2026-06-02）

### 問題描述

將 `meetchi-frontend` Cloud Run Ingress 改為外部（允許公開存取）後，瀏覽器訪問前端並嘗試 Google 登入時出現：

```
Error 400: redirect_uri_mismatch
發生原因：此應用程式傳送了無效要求
```

### 根本原因

Cloud Run 環境變數 `AUTH_URL` 的值為 `http://localhost:8080`（本機開發預設值），
NextAuth 使用此值組出 `redirect_uri` 參數：

```
redirect_uri = http://localhost:8080/api/auth/callback/google
```

Google OAuth 伺服器收到此 URI，與 Google Cloud Console 已登記的 Authorized Redirect URIs 不符，故拒絕請求。

### 修復方式

1. **更新 Cloud Run 環境變數**（已執行，2026-06-02 01:27 UTC+8）：

   ```bash
   gcloud run services update meetchi-frontend \
     --region=asia-southeast1 \
     --update-env-vars="AUTH_URL=https://meetchi-frontend-atro34poxq-as.a.run.app,NEXTAUTH_URL=https://meetchi-frontend-atro34poxq-as.a.run.app"
   # → Deployed revision: meetchi-frontend-00006-gp4
   ```

2. **在 Google Cloud Console 新增 Redirect URI**（需手動執行）：
   - 前往：https://console.cloud.google.com/apis/credentials
   - OAuth Client ID：`315688033208-qfnqg25jc2dmruep8ccbbpqhdlusdo9i`
   - 在 **Authorized redirect URIs** 加入：
     ```
     https://meetchi-frontend-atro34poxq-as.a.run.app/api/auth/callback/google
     ```

### 後續注意事項

- 每次更換 domain（例如換 LB 自訂網域 `meetchi.chimei.com.tw`），必須同步：
  1. 更新 Cloud Run `AUTH_URL`
  2. 在 Google OAuth Client 補登 Redirect URI
- Terraform 管控建議：將 `AUTH_URL` 納入 `cloudrun.tf` 的 env block（目前在 `ignore_changes` 內，需特別處理或改用 Secret Manager 管理）

---

## 二、Microsoft Entra ID (Azure AD) SSO 整合

### 2.1 背景與目標

奇美醫療使用 Microsoft 365（chimei.com.tw 為 Entra ID 租戶），員工帳號為 `xxx@mail.chimei.com.tw`。
MeetChi 登入需支援 Microsoft SSO，讓員工以公司帳號（而非個人 Google 帳號）登入，
符合企業 IT 安全規範，後續也可接 Azure RBAC / AD Groups。

### 2.2 實作範圍（本次 commit）

| 檔案 | 修改內容 |
|------|---------|
| `apps/backend/app/auth.py` | 新增 `verify_microsoft_token()`；自動偵測 token provider（Google / Microsoft） |
| `apps/frontend/src/auth.ts` | 加入 `MicrosoftEntraId` provider；session 補 `provider` 欄位；加 `AUTH_ALLOWED_DOMAIN` 限制 |
| `apps/frontend/src/app/login/page.tsx` | 新增 Microsoft 藍色登入按鈕（MS auth 未設定時自動隱藏） |

### 2.3 後端 Token 驗證流程

```
前端 → POST /api/... Authorization: Bearer <id_token>
         │
         ▼
     auth.py: _peek_token_provider(token)
         │ 讀取 JWT iss claim（不驗簽）
         ├── iss 含 microsoftonline.com → verify_microsoft_token()
         │       ├── 從 MS JWKS endpoint 取公鑰（快取 1 小時）
         │       ├── jose.jwt.decode() 驗簽 + audience
         │       └── 若 MS_TENANT_ID != "common"，嚴格驗 iss
         └── 其他 → verify_google_token()（原有邏輯不變）
```

### 2.4 需要的 Azure AD App Registration（資源申請中）

| 設定項目 | 值 |
|---------|-----|
| App 類型 | Single-tenant（僅 chimei.com.tw 租戶） |
| 帳號類型 | Accounts in this organizational directory only |
| Redirect URI (Web) | `https://meetchi-frontend-atro34poxq-as.a.run.app/api/auth/callback/microsoft-entra-id` |
| Redirect URI (Web) | `https://meetchi.chimei.com.tw/api/auth/callback/microsoft-entra-id`（LB 設好後加） |
| ID tokens | ✅ 啟用（Implicit grant 設定） |
| API permissions | `openid`, `profile`, `email`, `User.Read` |

### 2.5 需要設定的環境變數

#### Cloud Run（前端 `meetchi-frontend`）

```bash
gcloud run services update meetchi-frontend \
  --region=asia-southeast1 \
  --update-env-vars="\
AUTH_MICROSOFT_ENTRA_ID_ID=<Azure App Client ID>,\
AUTH_MICROSOFT_ENTRA_ID_SECRET=<Azure App Client Secret>,\
AUTH_MICROSOFT_ENTRA_ID_TENANT_ID=<chimei.com.tw Tenant UUID>,\
AUTH_ALLOWED_DOMAIN=mail.chimei.com.tw,\
NEXT_PUBLIC_MS_AUTH_ENABLED=true"
```

#### Cloud Run（後端 `meetchi-backend`）

```bash
gcloud run services update meetchi-backend \
  --region=asia-southeast1 \
  --update-env-vars="\
MS_CLIENT_ID=<Azure App Client ID>,\
MS_TENANT_ID=<chimei.com.tw Tenant UUID>,\
AUTH_ALLOWED_DOMAIN=mail.chimei.com.tw"
```

### 2.6 本機開發 `.env` 設定

```bash
# apps/frontend/.env.local
GOOGLE_CLIENT_ID=315688033208-qfnqg25jc2dmruep8ccbbpqhdlusdo9i.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<secret>
AUTH_SECRET=<secret>
AUTH_URL=http://localhost:3000

# MS（取得後填入）
AUTH_MICROSOFT_ENTRA_ID_ID=
AUTH_MICROSOFT_ENTRA_ID_SECRET=
AUTH_MICROSOFT_ENTRA_ID_TENANT_ID=
NEXT_PUBLIC_MS_AUTH_ENABLED=true  # 改為 true 即可顯示 MS 登入按鈕

# apps/backend/.env
AUTH_REQUIRED=false   # 本機測試
MS_CLIENT_ID=         # 取得後填入
MS_TENANT_ID=         # 取得後填入
```

### 2.7 MS OAuth 功能開關設計

`NEXT_PUBLIC_MS_AUTH_ENABLED` 為 build-time 環境變數：
- `false`（預設）：登入頁只顯示 Google 按鈕，MS 相關程式碼不執行
- `true`：顯示 Microsoft 藍色登入按鈕（排在 Google 按鈕上方，為主要入口）

後端的 `MS_CLIENT_ID` 也是開關：
- 未設定 → `verify_microsoft_token()` 直接回傳 `None` + 記錄 warning log，不影響 Google 驗證路徑

### 2.8 待辦（Azure 資源到位後）

- [ ] 在 Azure Portal 建立 App Registration（單租戶）
- [ ] 取得 Client ID / Client Secret / Tenant ID
- [ ] 更新 Cloud Run 環境變數（見 2.5）
- [ ] 重新 build & deploy 前端（`NEXT_PUBLIC_MS_AUTH_ENABLED` 是 build-time var，需重 build）
- [ ] 驗收：用 `jerry_tai@mail.chimei.com.tw` 帳號登入，確認 session 有 `provider: "microsoft"`
- [ ] 確認後端 `provider` 欄位有正確傳入 API header（`lib/api.ts` 確認 idToken 傳遞邏輯）

### 2.9 已知限制與設計決策

| 項目 | 決策 | 原因 |
|------|------|------|
| MS token 驗證用 JWKS | 選用 `python-jose` + JWKS endpoint | 無需向 MS 發請求驗證，純加密驗簽，效能好且離線可用 |
| JWKS 快取 1 小時 | 固定 TTL | MS JWKS 輪換頻率低，1 小時足夠；未來可改 Cache-Control 驗 |
| Google 維持原有驗證 | 不動 `google-auth` library | Google token 有特殊格式（audience 含 client_id），google-auth 處理最穩 |
| Provider 用 `iss` 自動偵測 | 不需前端傳 provider header | 減少 API Client 改動量，iss 是 JWT 標準欄位 |
| `AUTH_ALLOWED_DOMAIN` 雙層控制 | 前端 NextAuth `signIn` callback + 後端 `get_current_user` 都檢查 | 防止前端 bypass，後端不信任 session |

---

## 三、相關 Redirect URI 一覽（備查）

| 服務 | URL | 用途 |
|------|-----|------|
| Google OAuth | `https://meetchi-frontend-atro34poxq-as.a.run.app/api/auth/callback/google` | 目前 Cloud Run URL |
| Google OAuth | `https://meetchi.chimei.com.tw/api/auth/callback/google` | LB domain（未來加） |
| MS Entra ID | `https://meetchi-frontend-atro34poxq-as.a.run.app/api/auth/callback/microsoft-entra-id` | 目前 Cloud Run URL |
| MS Entra ID | `https://meetchi.chimei.com.tw/api/auth/callback/microsoft-entra-id` | LB domain（未來加） |

> ⚠️ `NEXT_PUBLIC_MS_AUTH_ENABLED` 是 Next.js build-time 變數，改值後必須重新 build image 才生效。
> 用 `gcloud run services update --update-env-vars` 無效，需觸發 Cloud Build。
