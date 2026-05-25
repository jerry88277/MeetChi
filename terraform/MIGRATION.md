# MeetChi 系統搬遷 SOP（GCP 跨專案 / Cloud Shell 環境）

> 將既有 MeetChi 部署從原 GCP 專案搬遷至企業內部的另一個 GCP 專案，全程於 **GCP Cloud Shell** 執行。
>
> 適用情境：企業 IT 限制只能用 Cloud Shell；不能裝本機 gcloud / terraform；新專案 ID 與既有 hardcoded 字串不同。
>
> 範圍：infrastructure（Terraform）+ docker images（Cloud Build）+ alembic migration（Cloud Run Job）+ 可選資料搬遷（Cloud SQL / GCS）。

---

## 0. 搬遷前盤點（離開原專案前必做）

### 0.1 原專案資訊備份

從**原** GCP 專案撈以下資料，存到企業內部的密碼管理工具（不要寫進 git）：

| 項目 | 取得指令（原專案） | 用途 |
|---|---|---|
| Hugging Face API token | `gcloud secrets versions access latest --secret=meetchi-hf-token --project=<old-project>` | 新環境 `terraform.tfvars` |
| Gemini API key（如有用 API key 模式） | `gcloud secrets versions access latest --secret=meetchi-gemini-api-key --project=<old-project>` | 新環境 `terraform.tfvars` |
| JWT secret_key | `gcloud secrets versions access latest --secret=meetchi-secret-key --project=<old-project>` | 新環境 `terraform.tfvars` |
| Discord webhook URL | Console / Secret Manager | 通知用，可選 |
| Cloud SQL DB 密碼 | `gcloud secrets versions access latest --secret=meetchi-db-password --project=<old-project>` | 僅在需要還原舊資料時用 |

> 安全紅線：上述 secrets 一律走密碼管理工具傳遞，不寫進 git、不貼 chat、不 echo 到 Cloud Shell stdout 後留存於 scrollback。

### 0.2 確認新專案前置條件

```bash
# 確認新 project_id 與 project_number
gcloud config set project <NEW_PROJECT_ID>
gcloud projects describe <NEW_PROJECT_ID> --format='value(projectNumber)'

# 確認 region 與 GPU 配額（L4 必須 >= 2，給 gpu-asr scaling）
gcloud compute regions describe asia-southeast1 --format='value(quotas)' | grep -i gpu

# 確認帳單已綁定
gcloud beta billing projects describe <NEW_PROJECT_ID>
```

如 GPU 配額不足，先在 GCP Console 提配額申請（一般 1–3 個工作天）。**沒 GPU 配額不要往下走**，後面 `terraform apply` 會在建 `meetchi-gpu-asr` 時失敗。

### 0.3 Clone repo 到 Cloud Shell

```bash
cd ~
git clone https://github.com/jerry88277/MeetChi.git
cd MeetChi
git checkout main
```

Cloud Shell 1 小時 idle 會 reset，但 `$HOME` 持久保存 5 GB，repo 不會掉。

---

## 1. 啟用必要的 GCP APIs

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudtasks.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  --project=<NEW_PROJECT_ID>
```

> `aiplatform.googleapis.com` 是 Gemini API（Vertex AI）需要的。如新專案位於有資料主權限制的地區（如 `europe-west*`），確認 Vertex AI 支援該 region；不行就改用 Gemini API key 模式（走 `generativelanguage.googleapis.com`）。

---

## 2. 建 Terraform state bucket

Terraform 用 GCS backend 存 state（避免 Cloud Shell reset 掉 local state）。

```bash
gcloud storage buckets create gs://<NEW_PROJECT_ID>-tfstate \
  --location=asia-southeast1 \
  --uniform-bucket-level-access \
  --project=<NEW_PROJECT_ID>

# 開啟版本控制 — state 損毀時可救回
gcloud storage buckets update gs://<NEW_PROJECT_ID>-tfstate --versioning
```

接著編輯 `terraform/backend.tf`（如尚未指向新 bucket）：

```hcl
terraform {
  backend "gcs" {
    bucket = "<NEW_PROJECT_ID>-tfstate"
    prefix = "meetchi/terraform/state"
  }
}
```

> 雞生蛋問題：bucket 必須先用 gcloud 手動建，不能用 Terraform 建（因為 Terraform 還沒有 state 可寫）。

---

## 3. 建 Artifact Registry repo

```bash
gcloud artifacts repositories create meetchi \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="MeetChi container images" \
  --project=<NEW_PROJECT_ID>
```

確認 repo 路徑：`asia-southeast1-docker.pkg.dev/<NEW_PROJECT_ID>/meetchi`

---

## 4. 建 `terraform.tfvars`（敏感資料，不 commit）

```bash
cd ~/MeetChi/terraform

cat > terraform.tfvars <<'EOF'
project_id          = "<NEW_PROJECT_ID>"
region              = "asia-southeast1"
zone                = "asia-southeast1-b"

# Secrets (從 0.1 盤點取得)
hf_auth_token       = "hf_xxx..."
secret_key          = "<JWT_SECRET_64_CHARS>"
gemini_api_key      = ""                  # 若用 ADC 不必填
discord_webhook_url = ""                  # 可選
EOF

# 確認 .gitignore 已排除
grep -q "terraform.tfvars" .gitignore || echo "terraform.tfvars" >> .gitignore
```

> `db_password` 由 Terraform 用 `random_password` 自動生成寫進 Secret Manager，**不要**手填。

---

## 5. 取代 hardcoded 字串（原專案殘留）

repo 內部分檔仍保留原專案 ID / project_number 作為 default。搬遷時須改：

```bash
cd ~/MeetChi

# 5.1 確認舊字串還有哪些檔案引用
grep -rn "project-51769b5e-7f0f-4a2f-80c" --include="*.tf" --include="*.yaml" --include="*.yml" --include="*.tsx" --include="*.ts" --include="*.py" .
grep -rn "705495828555" --include="*.tf" --include="*.yaml" --include="*.yml" --include="*.tsx" --include="*.ts" --include="*.py" .

# 5.2 批次取代
OLD_PROJECT="project-51769b5e-7f0f-4a2f-80c"
NEW_PROJECT="<NEW_PROJECT_ID>"
OLD_NUMBER="705495828555"
NEW_NUMBER="<NEW_PROJECT_NUMBER>"

# Linux sed (Cloud Shell 是 GNU sed)
find terraform cloudbuild* apps -type f \( -name "*.tf" -o -name "*.yaml" -o -name "*.yml" -o -name "*.tsx" -o -name "*.ts" \) \
  -exec sed -i "s/${OLD_PROJECT}/${NEW_PROJECT}/g; s/${OLD_NUMBER}/${NEW_NUMBER}/g" {} +

# 5.3 確認沒有漏網之魚
grep -rn "${OLD_PROJECT}\|${OLD_NUMBER}" --include="*.tf" --include="*.yaml" --include="*.yml" --include="*.tsx" --include="*.ts" .
```

> **重點檔案清單**（高頻命中）：
> - `terraform/variables.tf`（backend_image / gpu_asr_image / frontend_image 的 Artifact Registry default）
> - `terraform/cloudrun.tf`（service_account = `705495828555-compute@...`）
> - `cloudbuild-frontend.yaml` / `cloudbuild-backend.yaml` / `cloudbuild-gpu-asr.yaml`
> - `apps/frontend/.env.production`（NEXT_PUBLIC_API_URL）

---

## 6. Terraform init + apply

```bash
cd ~/MeetChi/terraform

# 6.1 init (連到剛建好的 GCS backend)
terraform init

# 6.2 預覽
terraform plan -out=tfplan

# 6.3 應用
terraform apply tfplan
```

預計建立的資源（首次 apply）：
- Cloud SQL `meetchi-db-pg` + database `meetchi` + user `postgres`
- GCS buckets：`<NEW_PROJECT_ID>-meetchi-db`、`<NEW_PROJECT_ID>-meetchi-audio`
- Cloud Tasks queues：`meetchi-transcription-queue`、`meetchi-summarization-queue`
- Secret Manager secrets：`meetchi-db-password`、`meetchi-hf-token`、`meetchi-secret-key`、`meetchi-gemini-api-key`
- Cloud Run services：`meetchi-backend`、`meetchi-frontend`、`meetchi-gpu-asr`（會用 `variables.tf` 內 image default 拉，**首次拉不到**，會卡住 → 進 step 7 重 deploy）
- Cloud Run Job：`db-migrate-v19`

> 預期：首次 apply 在建 Cloud Run service 時會 fail（image 不存在），這是預期狀態。先讓 SQL / Secrets / Buckets / Tasks 建好，再進下一步 build image，最後重 apply。
>
> 或先把 `variables.tf` 內的 image default 暫時指向 `gcr.io/cloudrun/hello`，apply 成功後再走 step 7 build + step 9 deploy 覆寫。

---

## 7. Build Docker images（Cloud Build）

```bash
cd ~/MeetChi

# 7.1 Backend
gcloud builds submit --config=cloudbuild-backend.yaml --project=<NEW_PROJECT_ID>

# 7.2 GPU ASR
gcloud builds submit --config=cloudbuild-gpu-asr.yaml --project=<NEW_PROJECT_ID>

# 7.3 Frontend（注意 NEXT_PUBLIC_API_URL 必須在 build time 注入）
# 先取得 backend URL
BACKEND_URL=$(gcloud run services describe meetchi-backend \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID> \
  --format='value(status.url)')

# 暫存到 cloudbuild substitutions 或環境變數
gcloud builds submit \
  --config=cloudbuild-frontend.yaml \
  --substitutions=_API_URL="${BACKEND_URL}" \
  --project=<NEW_PROJECT_ID>
```

> **frontend 的 NEXT_PUBLIC_API_URL 必須在 docker build 階段注入**（Next.js 把 `NEXT_PUBLIC_*` 字串編譯進 bundle），不能在 Cloud Run runtime env 覆寫。每換一次 backend URL 就要 rebuild frontend。

---

## 8. 跑 alembic migration

```bash
gcloud run jobs execute db-migrate-v19 \
  --region=asia-southeast1 \
  --project=<NEW_PROJECT_ID> \
  --wait

# 確認 exit code
gcloud run jobs executions describe <execution-name> \
  --region=asia-southeast1 \
  --project=<NEW_PROJECT_ID> \
  --format='value(status.completionStatus)'
```

> 如 fail，先看 log：
> ```
> gcloud run jobs executions logs read <execution-name> --region=asia-southeast1 --project=<NEW_PROJECT_ID>
> ```
> 常見錯：DB user/password 還沒寫進 Secret Manager（step 6 必須先成功）、Cloud SQL connector 沒掛上。

---

## 9. Deploy services + 回填 frontend URL

如 step 6 用 hello-world 跳過 image 拉取問題，這步補上正確 image：

```bash
# Backend
gcloud run deploy meetchi-backend \
  --image=asia-southeast1-docker.pkg.dev/<NEW_PROJECT_ID>/meetchi/meetchi-backend:latest \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID>

# GPU ASR
gcloud run deploy meetchi-gpu-asr \
  --image=asia-southeast1-docker.pkg.dev/<NEW_PROJECT_ID>/meetchi/meetchi-gpu-asr:latest \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID>

# Frontend
gcloud run deploy meetchi-frontend \
  --image=asia-southeast1-docker.pkg.dev/<NEW_PROJECT_ID>/meetchi/meetchi-frontend:latest \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID>

# 回填 gpu_asr_service_url 給 backend
GPU_ASR_URL=$(gcloud run services describe meetchi-gpu-asr \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID> --format='value(status.url)')

gcloud run services update meetchi-backend \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID> \
  --update-env-vars="GPU_ASR_SERVICE_URL=${GPU_ASR_URL}"
```

---

## 10.（可選）資料搬遷

僅在「需要保留舊環境的會議資料」時才做。新環境若是 fresh start 可跳過。

### 10.1 Cloud SQL 資料 export → import

```bash
# 原專案：export
gcloud sql export sql meetchi-db-pg \
  gs://<OLD_PROJECT_ID>-meetchi-db/migration-$(date +%Y%m%d).sql \
  --database=meetchi \
  --project=<OLD_PROJECT_ID>

# 跨專案複製 dump
gcloud storage cp \
  gs://<OLD_PROJECT_ID>-meetchi-db/migration-*.sql \
  gs://<NEW_PROJECT_ID>-meetchi-db/

# 新專案：import（先停 backend 避免寫衝突）
gcloud run services update meetchi-backend \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID> \
  --min-instances=0 --max-instances=0

gcloud sql import sql meetchi-db-pg \
  gs://<NEW_PROJECT_ID>-meetchi-db/migration-*.sql \
  --database=meetchi \
  --project=<NEW_PROJECT_ID>

# 恢復 scaling
gcloud run services update meetchi-backend \
  --region=asia-southeast1 --project=<NEW_PROJECT_ID> \
  --min-instances=0 --max-instances=3
```

> 跨專案 SQL export/import 需要兩邊的 Cloud SQL service account 都有對應 GCS bucket 的 `objectAdmin` 權限。出錯先看 `gcloud sql operations list`。

### 10.2 GCS audio bucket rsync

```bash
gcloud storage rsync \
  gs://<OLD_PROJECT_ID>-meetchi-audio \
  gs://<NEW_PROJECT_ID>-meetchi-audio \
  --recursive --project=<NEW_PROJECT_ID>
```

---

## ⚠️ 注意事項（按踩坑頻率排序）

### 高頻必踩

1. **Cloud Shell 1 小時 idle 會 reset**：長指令（`terraform apply`、`gcloud builds submit`）建議掛 `nohup` 或 `tmux`：
   ```bash
   tmux new -s deploy
   # 進 tmux 後跑長指令
   # Ctrl+B D 脫離；重連用 tmux attach -t deploy
   ```
2. **NEXT_PUBLIC_API_URL 必須 build-time 注入**：runtime env 改了沒用。每換 backend URL 都要 rebuild frontend。
3. **project_number ≠ project_id**：`705495828555-compute@developer.gserviceaccount.com` 是原專案的 default compute SA，搬遷後要換成新專案的 project_number。漏改會導致 Cloud Run 起不來（SA 不存在）。
4. **TF state bucket 雞生蛋**：bucket 必須先用 gcloud 手動建，不能寫進 Terraform。
5. **GPU 配額**：新專案的 L4 配額預設可能是 0，要先申請。沒配額時 `terraform apply` 會在 `meetchi-gpu-asr` 卡住，且不會自動 retry。
6. **Secrets 必須重新發**：HF token / Gemini key / JWT secret 不能跨專案共用（DB password 由 TF 自動生成新值）。

### 中頻

7. **Service account 自動生成**：新專案的 default compute SA 在啟用 Compute API 後才會存在（step 1 後）。如 SA 還沒生成就跑 TF apply 會 fail。
8. **Cloud Tasks queue location**：必須與 Cloud Run service 同 region，跨 region 會 403。
9. **Vertex AI / Gemini location**：新專案如在歐盟，要確認 Vertex AI 該 region 支援 Gemini Flash/Pro 模型；否則改 location 或改用 generativelanguage.googleapis.com API key 模式。
10. **DB user password**：Terraform `random_password` 每次 apply 都會檢查；首次寫進 Secret Manager 後，後續 apply 會走 `ignore_changes = [secret_data]` 不動。要手動 rotate 走 `gcloud secrets versions add`。

### 低頻但會卡死人

11. **NextAuth / SSO**：如企業環境用不同的 OAuth provider（Google Workspace → Azure AD），要改 frontend 的 NextAuth 設定 + backend 的 token 驗證邏輯，這超出純搬遷範圍。
12. **Discord webhook**：企業內部如禁用 Discord，改 Teams webhook 要動 `apps/backend/app/notifications/`。
13. **Admin endpoint IAM**：原專案的 admin 白名單 (`pjerry@...`) 寫在 code 裡，新環境的 admin email 要改 `apps/backend/app/routes/admin.py`。

---

## 驗證 Checklist

deploy 完成後，按順序驗證：

```bash
BACKEND=$(gcloud run services describe meetchi-backend --region=asia-southeast1 --project=<NEW_PROJECT_ID> --format='value(status.url)')
FRONTEND=$(gcloud run services describe meetchi-frontend --region=asia-southeast1 --project=<NEW_PROJECT_ID> --format='value(status.url)')
GPU_ASR=$(gcloud run services describe meetchi-gpu-asr --region=asia-southeast1 --project=<NEW_PROJECT_ID> --format='value(status.url)')

# 1. Backend health
curl "${BACKEND}/health"
# 期望：{"status":"ok","db":"connected"}

# 2. GPU ASR health
curl "${GPU_ASR}/health"
# 期望：{"status":"ok","model_loaded":true}

# 3. Frontend HTTP 200
curl -I "${FRONTEND}"
# 期望：HTTP/2 200

# 4. Cloud SQL 連線（從 backend pod 視角）
curl "${BACKEND}/api/admin/rag-status" -H "Authorization: Bearer <admin-token>"

# 5. 上傳 1 個小 audio file（< 1 min），確認 transcription pipeline 完整
# 從 frontend UI 操作；觀察 Cloud Run logs
gcloud run services logs tail meetchi-backend --region=asia-southeast1 --project=<NEW_PROJECT_ID>
```

全綠 → 搬遷完成。任何一項紅 → 對照 [OPERATIONS.md](./OPERATIONS.md) 的 troubleshooting 章節。

---

## 回滾策略

如新環境 fail 且需回到原專案：

1. **DNS / Frontend URL 還沒切換**：直接停掉新專案的 Cloud Run services（`min-instances=0, max-instances=0`），原專案不受影響。
2. **已切換但要回滾**：
   - 把企業內部的 DNS / proxy 指回原專案的 Cloud Run URL
   - 如做了資料搬遷，原專案資料仍在（export 是讀取，不破壞原 DB）
3. **新專案完全廢棄**：`terraform destroy`（先確認 GCS bucket 內無重要資料，TF state bucket 要手動刪）

> 不建議直接 delete 整個新 GCP project — billing reconciliation 會多收 30 天 grace period 費用。

---

## 參考文件

- [DEPLOYMENT.md](./DEPLOYMENT.md) — 既有環境的部署流程
- [OPERATIONS.md](./OPERATIONS.md) — 維運手冊（admin endpoint / 故障處理 / DR）
- [variables.tf](./variables.tf) — Terraform 變數定義
- [cloudrun.tf](./cloudrun.tf) — Cloud Run 服務定義

---

**Last updated**: 2026-05-25
**Maintainer**: jerry88277@gmail.com
