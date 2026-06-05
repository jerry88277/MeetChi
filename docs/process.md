# MeetChi 前端公開訪問問題 — 盤點與解決方案

> 建立日期：2026-06-01
> 問題描述：直接透過 URL 訪問 MeetChi 前端，得到 `Error: Forbidden – Your client does not have permission to get URL / from this server.`

---

## 一、問題根因（三層缺口）

### 第一層（最關鍵）：Cloud Run IAM 沒有開放 `allUsers`

| 服務 | 現有 IAM 成員 | 缺少 |
|------|--------------|------|
| `meetchi-frontend` | `domain:chimei.com.tw`、`user:jerry_tai@mail.chimei.com.tw` | `allUsers` |
| `meetchi-backend`  | `user:jerry_tai@mail.chimei.com.tw` | `allUsers`、`domain:chimei.com.tw` |

瀏覽器直接打 Cloud Run URL → Cloud Run 在容器層之前就擋掉（GCP 基礎設施層）→ `403 Forbidden`，Next.js 根本沒機會接到請求。

### 第二層：GCP 組織政策擋住 `allUsers`

Terraform `cloudrun.tf` 中已標記：

```hcl
# IAM - Allow unauthenticated access (public API)
# Commented out due to GCP Org Policy constraints/iam.managed.allowedPolicyMembers
# which prohibits public access (allUsers invoker).
```

**組織政策** `constraints/iam.managed.allowedPolicyMembers` 阻止對此專案設定 `allUsers`。

- **GCP 組織**：`chimei.com.tw`（ID: 643263103833）
- **專案路徑**：Folder `id=5367138862` → `prj-ai-meetchi-du`

### 第三層：後端也沒開放 `domain:chimei.com.tw`

即使前端能訪問，前端打後端 API 時後端同樣回 403。

---

## 二、解決方案評估

| 方案 | 難度 | 是否需 Org Policy 例外 | 說明 |
|------|------|----------------------|------|
| A. 申請 Org Policy 例外 | 低 | ✅ 需要 | 讓 IT 對此專案豁免，執行 `gcloud ... add-iam-policy-binding allUsers` |
| **B. Load Balancer + IAP** | **中** | **❌ 不需要** | **IAP 在 LB 層做 Google 登入驗證，Cloud Run 改為只接受 LB 流量** |
| C. 後端補上 `domain:chimei.com.tw` | 低 | ❌ 不需要 | 僅修後端 IAM，但瀏覽器直訪 Cloud Run 仍 403（browser 不帶 Bearer token）|

**建議採用方案 B（IAP + Load Balancer）**，無需申請組織政策例外，符合企業安全規範。

---

## 三、IAP 方案詳細需求（方案 B）

### 3.1 現況盤點

| 項目 | 現況 |
|------|------|
| `compute.googleapis.com` | ✅ 已啟用 |
| `iap.googleapis.com` | ✅ 已啟用 |
| `certificatemanager.googleapis.com` | ❌ 未啟用 |
| Global Load Balancer | ❌ 無 |
| Global Static IP | ❌ 無 |
| SSL 憑證 | ❌ 無 |
| 自訂 Domain（e.g. `meetchi.chimei.com.tw`） | ❌ 未設定 |

### 3.2 架構示意

```
Internet
   │
   ▼
Forwarding Rule  (Global Static IP:443)
   │
   ▼
HTTPS Target Proxy  ──── SSL Certificate (meetchi.chimei.com.tw)
   │
   ▼
URL Map
   ├── /api/*  → Backend Service  (meetchi-backend NEG)
   └── /*      → Backend Service  (meetchi-frontend NEG)
                      │
                   [IAP]  ← Google 登入驗證在此層發生（browser 自動導向）
                      │
                      ▼
              Serverless NEG
       ┌────────────────────────┐
       │  Cloud Run             │
       │  ingress: LB-only      │  ← 只接受 LB 流量，無需 allUsers
       └────────────────────────┘
```

### 3.3 需要啟用的 GCP API

```bash
gcloud services enable certificatemanager.googleapis.com
# compute.googleapis.com 已啟用
# iap.googleapis.com 已啟用
```

### 3.4 需要建立的 GCP 資源

| 資源 | 數量 | 說明 |
|------|------|------|
| Global External Static IP | 1 | 固定 IP，綁給 LB Forwarding Rule |
| Serverless NEG | 2 | 各自指向 `meetchi-frontend`、`meetchi-backend` Cloud Run |
| Backend Service | 2 | 掛 NEG，並在此啟用 IAP |
| Google-managed SSL Certificate | 1 | 綁自訂 domain，自動申請與更新（免費） |
| URL Map | 1 | 路由規則：`/api/*` → backend，`/*` → frontend |
| HTTPS Target Proxy | 1 | 綁 SSL Certificate |
| Forwarding Rule | 1 | Global IP + Port 443 → Target Proxy |
| IAP OAuth Client | 1 | 建立於 API Console，需 OAuth consent screen（設為 Internal） |

### 3.5 IAM 權限調整

| 對象 | Role | 說明 |
|------|------|------|
| `domain:chimei.com.tw` | `roles/iap.httpsResourceAccessor` | 讓所有 chimei.com.tw 帳號可通過 IAP |
| Cloud Run services（兩個） | ingress 改為 `internal-and-cloud-load-balancing` | **核心設定，繞過 Org Policy 限制** |

### 3.6 Cloud Run Ingress 設定變更

```bash
# 前端：只接受 LB 流量
gcloud run services update meetchi-frontend \
  --ingress internal-and-cloud-load-balancing \
  --region asia-southeast1

# 後端：只接受 LB 流量
gcloud run services update meetchi-backend \
  --ingress internal-and-cloud-load-balancing \
  --region asia-southeast1
```

> ⚠️ 執行後，直接訪問 Cloud Run 原始 URL（`*.run.app`）會回 403，這是預期行為。
> 僅可透過 LB 的 domain（`meetchi.chimei.com.tw`）訪問。

### 3.7 需協調的外部事項

| 事項 | 負責方 |
|------|--------|
| 申請自訂 domain（e.g. `meetchi.chimei.com.tw`） | IT / DNS 管理員 |
| DNS A Record：`meetchi.chimei.com.tw` → Global Static IP | IT / DNS 管理員 |
| OAuth consent screen 設定為 **Internal**（僅 chimei org） | GCP 專案擁有者（需 `roles/owner` 或 `roles/iap.admin`） |
| IAP OAuth Client 建立 | GCP 專案擁有者 |

### 3.8 不需要的項目

- ❌ 不需申請 Org Policy 例外
- ❌ 不需 `allUsers` invoker
- ❌ 不需 VPC / Private Service Connect（Serverless NEG 走 Google 內部網路）
- ❌ 不需 Cloud Armor（可選，之後加強安全性用）

---

## 四、使用者訪問體驗（方案 B 完成後）

1. 輸入 `https://meetchi.chimei.com.tw`
2. 若未登入 Google → **自動導向 Google 登入頁**（IAP 處理，無需手動操作）
3. 用 `@chimei.com.tw` Google 帳號登入
4. 自動跳回 MeetChi 首頁 → 再由 Next.js middleware 引導至 `/dashboard`
5. 後續操作完全無感，Session 存活期間不需重新登入

---

## 五、後續行動項目

- [ ] 確認可用的自訂 domain（與 IT 協調）
- [ ] 啟用 `certificatemanager.googleapis.com`
- [ ] 建立 IAP OAuth consent screen（設 Internal）
- [ ] 撰寫 Terraform `iap.tf`（Load Balancer + NEG + IAP 資源）
- [ ] 申請 DNS A Record 指向 Global Static IP
- [ ] 執行 Cloud Run ingress 變更
- [ ] 驗收：用 chimei 帳號瀏覽器直接訪問，確認自動登入流程正常
