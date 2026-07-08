# 基礎設施 — 資料庫與持久化設計日誌

> 記錄 MeetChi 後端資料持久化架構的決策過程、踩坑紀錄與最佳實踐，
> 供日後維運、新成員上手、以及相似問題排查使用。

---

## 一、背景

MeetChi 後端使用 FastAPI + SQLAlchemy，資料庫連線由 `database.py` 的
`DATABASE_URL` 環境變數控制，預設值為：

```python
# apps/backend/app/database.py
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/sql_app.db")
```

這個預設值在**本地開發時**很方便（零設定即可跑起來），但在 **Cloud Run
正式環境**卻是一顆定時炸彈。

---

## 二、INC-016：SQLite 暫存導致資料全數消失

### 2.1 事件經過

| 時間 | 事件 |
|------|------|
| 2026-05-29 | Cloud SQL `meetchi-db-pg`（Postgres 15）建立完成 |
| 2026-05-29～06-08 | 多次 backend 部署（revision 00001～00012） |
| 2026-06-08 03:00 | UAT 測試切換帳號後發現「所有會議記錄不見了」 |
| 2026-06-08 03:06 | 確認根本原因：`DATABASE_URL` 未設定，backend 一直使用 SQLite |
| 2026-06-08 03:10 | 設定 `DATABASE_URL` 指向 Cloud SQL，revision 00013 起恢復正常 |

### 2.2 根本原因

```
環境變數 DATABASE_URL 從未被設定到 Cloud Run service。
  ↓
backend 使用 default: sqlite:////tmp/sql_app.db
  ↓
Cloud Run 每次 cold start 或 revision deploy → /tmp 清空
  ↓
所有會議資料消失（revision 間不共享 /tmp）
```

**Cloud SQL 一直都存在且有資料，但完全沒被使用。**

### 2.3 影響範圍

- **遺失資料**：2026-05-29 之後以 SQLite 寫入的測試會議（數量未知，SQLite 已被清空）
- **保留資料**：Cloud SQL 中 3 筆早期歷史記錄（revision 00001 之前寫入）
  - 勤威國際 — 自駕導航議題討論
  - 鴻才討論
  - 錄製 (2)
- **受影響功能**：所有 meeting CRUD、轉錄、摘要結果

### 2.4 修復方式

```bash
# 取得 DB 密碼
DB_PASS=$(gcloud secrets versions access latest --secret="meetchi-db-password" --project=prj-ai-meetchi-du)

# Cloud SQL Unix socket 連線字串（Cloud Run 內部走 Unix socket，不走 TCP）
DATABASE_URL="postgresql://postgres:${DB_PASS}@/meetchi?host=/cloudsql/prj-ai-meetchi-du:asia-southeast1:meetchi-db-pg"

# 設定到 Cloud Run backend service
gcloud run services update meetchi-backend \
  --region=asia-southeast1 \
  --project=prj-ai-meetchi-du \
  "--update-env-vars=^||^DATABASE_URL=${DATABASE_URL}"
```

> **注意**：`--update-env-vars` 使用 `^||^` 作為 delimiter，避免密碼中的
> 特殊字元（`,` 等）被誤判為分隔符。

### 2.5 驗證方式

```bash
BACKEND_URL="https://meetchi-backend-315688033208.asia-southeast1.run.app"
curl -s "$BACKEND_URL/api/v1/meetings?skip=0&limit=5" | python3 -c "
import json,sys; data=json.load(sys.stdin); print('Count:', len(data))
"
# 預期：Count > 0（應看到歷史會議）
```

---

## 三、Cloud SQL 連線架構

### 3.1 連線方式

Cloud Run → Cloud SQL 支援兩種方式：

| 方式 | URL 格式 | 說明 |
|------|---------|------|
| **Unix Socket（推薦）** | `postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE` | Cloud Run 原生支援，不需開放 public IP，延遲最低 |
| TCP（不推薦） | `postgresql://user:pass@PUBLIC_IP/dbname` | 需要 Cloud SQL Auth Proxy 或開放 public IP，安全性較差 |

**目前使用 Unix Socket**，連線資訊：

```
Instance：  prj-ai-meetchi-du:asia-southeast1:meetchi-db-pg
DB 名稱：   meetchi
使用者：    postgres
密碼：      Secret Manager → meetchi-db-password
```

Cloud Run service 設定中已有 `run.googleapis.com/cloudsql-instances`
annotation，這是 Cloud Run 自動建立 Unix socket 的必要條件。

### 3.2 Cloud SQL Proxy（自動）

Cloud Run 啟動時，若 `cloudsql-instances` annotation 存在，GCP 會自動
在容器內建立 Unix socket，路徑為：

```
/cloudsql/prj-ai-meetchi-du:asia-southeast1:meetchi-db-pg/.s.PGSQL.5432
```

**開發者無需手動啟動 Cloud SQL Auth Proxy。**

---

## 四、本地開發 vs. Cloud Run 環境差異

| | 本地開發 | Cloud Run |
|---|---------|----------|
| 資料庫 | SQLite（`/tmp/sql_app.db`）| Postgres 15（Cloud SQL）|
| 資料持久化 | 重啟後消失 ✗ | 持久化 ✓ |
| `DATABASE_URL` | 不設定（用預設） | 必須設定 |
| 連線方式 | 直接存取本地檔案 | Unix Socket via Cloud SQL Proxy |

### 本地開發啟動指令

```bash
# 使用 SQLite（快速測試，資料不持久）
cd apps/backend
uvicorn app.main:app --reload

# 使用本地 Postgres（需要先 docker run postgres）
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/meetchi" \
  uvicorn app.main:app --reload
```

### Cloud Run 必要環境變數

```
DATABASE_URL  = postgresql://postgres:<pass>@/meetchi?host=/cloudsql/<instance>
AUTH_SECRET   = <同 frontend 的 AUTH_SECRET>
SECRET_KEY    = <from Secret Manager meetchi-secret-key>
```

---

## 五、預防措施與建議

### 5.1 已實施

- [x] `DATABASE_URL` 設定於 Cloud Run backend service（revision 00013 起）
- [x] INC-016 記錄於 `docs/operations/incident-log.md`

### 5.2 建議後續實施

#### (A) Startup 自我檢查

在 `app/main.py` 啟動時加入警告：

```python
# main.py startup 事件
@app.on_event("startup")
async def startup_checks():
    if DATABASE_URL.startswith("sqlite"):
        import logging
        logging.getLogger("meetchi").warning(
            "⚠️  DATABASE_URL 指向 SQLite（%s）。"
            "Cloud Run 環境下資料將在 cold start 後消失，"
            "請確認是否為預期行為。", DATABASE_URL
        )
```

#### (B) Cloud Build / CD Pipeline 加入檢查

部署前驗證 `DATABASE_URL` 已設定且不是 SQLite：

```bash
# cloudbuild.yaml 加入 deploy 前驗證 step
- name: 'gcr.io/cloud-builders/gcloud'
  id: 'verify-db-url'
  entrypoint: bash
  args:
    - '-c'
    - |
      DB_URL=$(gcloud run services describe meetchi-backend \
        --region=asia-southeast1 --format='value(spec.template.spec.containers[0].env[DATABASE_URL])')
      if [[ "$DB_URL" == sqlite* ]] || [[ -z "$DB_URL" ]]; then
        echo "ERROR: DATABASE_URL not set or pointing to SQLite!"
        exit 1
      fi
```

#### (C) DB Migration 自動化

目前 `main.py` 在 startup 執行 `Base.metadata.create_all(engine)`（建表
但不做 migration）。若 schema 有變動，應使用 **Alembic** 管理：

```bash
cd apps/backend
pip install alembic
alembic init alembic
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

#### (D) Cloud SQL 定期備份確認

Cloud SQL 預設開啟自動備份（每日），確認設定：

```bash
gcloud sql instances describe meetchi-db-pg \
  --project=prj-ai-meetchi-du \
  --format='value(settings.backupConfiguration)'
```

---

## 六、常用維運指令

```bash
PROJECT="prj-ai-meetchi-du"
INSTANCE="meetchi-db-pg"
REGION="asia-southeast1"

# 查詢 Cloud SQL 狀態
gcloud sql instances describe $INSTANCE --project=$PROJECT

# 連線進 DB（需要有 Cloud SQL Client 權限）
gcloud sql connect $INSTANCE --user=postgres --project=$PROJECT
# 進去之後：\c meetchi → SELECT COUNT(*) FROM meetings;

# 查看 DB 備份列表
gcloud sql backups list --instance=$INSTANCE --project=$PROJECT

# 從備份還原（緊急用）
gcloud sql backups restore <BACKUP_ID> \
  --restore-instance=$INSTANCE \
  --project=$PROJECT

# 更新 DATABASE_URL（密碼輪換後使用）
DB_PASS=$(gcloud secrets versions access latest --secret="meetchi-db-password" --project=$PROJECT)
DATABASE_URL="postgresql://postgres:${DB_PASS}@/meetchi?host=/cloudsql/${PROJECT}:${REGION}:${INSTANCE}"
gcloud run services update meetchi-backend \
  --region=$REGION --project=$PROJECT \
  "--update-env-vars=^||^DATABASE_URL=${DATABASE_URL}"
```

---

## 五、GCP 環境參數真相表（Source of Truth）— 供專案環境搬遷使用

> **背景（2026-07-08）**：部署詳情頁路由統一（方案 2）時發現，各文件對 GCP
> 專案的識別碼**嚴重不一致**。`grep` 全 repo 統計：
> `project-51769b5e-7f0f-4a2f-80c`×45、`prj-ai-meetchi-du`×36、
> `705495828555`×25、`atro34poxq`×22、`315688033208`×20。
> 其中 `.agent/workflows/gcp-deploy.md` 內的 project ID 與 `705495828555` URL
> **已過時**，若照抄會部署到錯誤/不存在的目標。為避免後續環境搬遷再次踩雷，
> 於此建立單一真相表。

### 5.1 目前正式環境（2026-07-08 由 live `gcloud` 實測確認）

| 參數 | 現行正確值 |
|------|-----------|
| GCP Project ID | `prj-ai-meetchi-du` |
| GCP Project Number | `315688033208` |
| Region | `asia-southeast1` |
| Artifact Registry | `asia-southeast1-docker.pkg.dev/prj-ai-meetchi-du/meetchi` |
| Frontend Service | `meetchi-frontend` |
| Backend Service | `meetchi-backend` |
| GPU ASR Service | `meetchi-gpu-asr` |
| Frontend URL（hash） | `https://meetchi-frontend-atro34poxq-as.a.run.app` |
| Frontend URL（proj-num） | `https://meetchi-frontend-315688033208.asia-southeast1.run.app` |
| Backend URL（hash） | `https://meetchi-backend-atro34poxq-as.a.run.app` |
| Backend URL（proj-num） | `https://meetchi-backend-315688033208.asia-southeast1.run.app` |
| Cloud SQL Instance | `meetchi-db-pg`（POSTGRES_15）|
| Cloud SQL Connection Name | `prj-ai-meetchi-du:asia-southeast1:meetchi-db-pg` |

> 註：同一 Cloud Run 服務同時有「hash 形式」（`-atro34poxq-as.a.run.app`）與
> 「project-number 形式」（`-315688033208.asia-southeast1.run.app`）兩種 URL，
> 兩者皆有效、皆導向同一服務（health 實測皆 200）。`cloudbuild-frontend.yaml`
> 的 `NEXT_PUBLIC_API_URL` 用 project-number 形式，Dockerfile ARG 預設用 hash
> 形式，兩者等價（Belt & Suspenders）。

### 5.2 ⛔ 已過時、禁止再使用的識別碼

| 過時值 | 出處（需清理） | 說明 |
|--------|---------------|------|
| `project-51769b5e-7f0f-4a2f-80c` | `.agent/workflows/gcp-deploy.md` 等 | 舊 project ID，已非現行環境 |
| `705495828555` | `gcp-deploy.md` 內所有 `*.run.app` URL | 舊 project number，URL 已失效 |

> **教訓**：部署前**一律**先 `gcloud run services list --project prj-ai-meetchi-du`
> 用實測結果核對，不可盲信 workflow 文件內寫死的 project/URL。

### 5.3 專案環境搬遷檢查清單（下次 migration 時逐項執行）

搬遷到新 GCP 專案時，以下位置的識別碼**全部**要同步更新（以本表為準）：

1. `terraform/**/*.tf` + `terraform.tfvars`（env var / secret 的 Source of Truth）。
2. `apps/frontend/cloudbuild-frontend.yaml` 的 `NEXT_PUBLIC_API_URL`。
3. `apps/frontend/Dockerfile` 的 `ARG NEXT_PUBLIC_API_URL` 預設值。
4. `.agent/workflows/gcp-deploy.md`（Project ID / Project Number / 所有 `*.run.app` URL / Artifact Registry 路徑）。
5. Backend `DATABASE_URL` → 新的 Cloud SQL Connection Name。
6. OAuth redirect URI / NextAuth callback（見 `devlog-ms-oauth.md`）需登記新網域。
7. 搬遷後跑 §四維運指令 + `/api/health`、`/health` 雙端 smoke test，並確認流量鎖在最新 revision（`--to-latest`）。

> 完成搬遷後，回來更新本 §5.1 表格為新環境值，並把舊值移入 §5.2。
