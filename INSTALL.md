# MeetChi 安裝說明手冊

## 📋 系統架構概覽

MeetChi 是一個即時語音轉錄與翻譯平台，由以下元件組成：

| 元件 | 技術棧 | 用途 |
|-----|-------|------|
| **Frontend** | Next.js 16 + React 19 | Web Dashboard |
| **Backend API** | FastAPI + Python 3.11 | REST API + WebSocket |
| **LLM Service** | Flask + Transformers + CUDA | 語音辨識 + 摘要生成 |
| **Database** | PostgreSQL 15 | 資料持久化 |
| **Tauri Client** | Rust + Next.js | 桌面應用程式 |

---

## 🔧 前置需求

### 開發環境

- **Node.js** >= 20.x
- **Python** >= 3.11
- **Rust** (for Tauri client)
- **Docker** (for containerized deployment)
- **Git**

### GCP 部署（選用）

- Google Cloud Platform 帳號
- Terraform >= 1.0
- gcloud CLI

---

## 🖥️ Frontend (Web Dashboard)

### 位置
```
apps/frontend/
```

### 安裝與執行

```bash
cd apps/frontend
npm install
npm run dev
```

### 環境變數

建立 `.env.local` 檔案：

```env
# NextAuth.js
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-nextauth-secret

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 相依套件

- next: 16.0.1
- react: 19.2.0
- next-auth: 5.0.0-beta.30
- tailwindcss: 4.x

---

## 🔙 Backend API

### 位置
```
apps/backend/
```

### 安裝與執行

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 環境變數

複製 `.env.example` 為 `.env` 並填入：

```env
# === Authentication ===
AUTH_REQUIRED=true
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
ADMIN_EMAILS=admin@example.com,your-email@gmail.com

# === Database ===
DATABASE_URL=postgresql://meetchi_user:password@localhost:5432/meetchi

# === LLM Service ===
LLM_SERVICE_URL=http://localhost:8001

# === Cloud Tasks (GCP 部署) ===
CLOUD_TASKS_QUEUE=meetchi-summarization-queue
CLOUD_TASKS_LOCATION=asia-southeast1
GCP_PROJECT_ID=your-project-id
```

### 主要相依套件

| 套件 | 版本 | 用途 |
|-----|------|------|
| fastapi | >= 0.100.0 | Web 框架 |
| uvicorn | >= 0.23.0 | ASGI 伺服器 |
| sqlalchemy | >= 2.0.0 | ORM |
| psycopg2-binary | >= 2.9.0 | PostgreSQL 驅動 |
| google-cloud-tasks | >= 2.14.0 | 非同步任務 |
| python-jose | >= 3.3.0 | JWT 認證 |
| httpx | >= 0.24.0 | HTTP 客戶端 |

---

## 🤖 LLM Service (GPU)

### 位置
```
apps/llm_service/
```

### 安裝與執行

```bash
cd apps/llm_service
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python main.py
```

### 環境變數

```env
# Hugging Face Token (for private models)
HF_TOKEN=hf_your_token_here

# Model Configuration
MODEL_NAME=MediaTek-Research/Breeze-7B-Instruct-v1_0
DEVICE=cuda  # or cpu

# Server
PORT=8001
```

### 主要相依套件

| 套件 | 版本 | 用途 |
|-----|------|------|
| flask | >= 2.0.0 | Web 框架 |
| transformers | >= 4.35.0 | LLM 推論 |
| accelerate | >= 0.25.0 | GPU 加速 |
| bitsandbytes | >= 0.41.0 | 4-bit 量化 |
| mtkresearch | >= 0.3.0 | Breeze 模型 |

### GPU 需求

- NVIDIA GPU with CUDA 12.1+
- 至少 16GB VRAM (for 7B model)
- 推薦: NVIDIA L4 / RTX 4090 / A100

---

## 🗄️ Database (PostgreSQL)

### 資料庫設定

| 設定項 | 值 |
|-------|---|
| **資料庫版本** | PostgreSQL 15 |
| **資料庫名稱** | `meetchi` |
| **使用者名稱** | `meetchi_user` |
| **預設 Port** | 5432 |

### 本地安裝

1. 安裝 PostgreSQL 15
2. 建立資料庫與使用者：

```sql
CREATE DATABASE meetchi;
CREATE USER meetchi_user WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE meetchi TO meetchi_user;
```

3. 執行 migrations：

```bash
cd apps/backend
alembic upgrade head
```

### GCP Cloud SQL

Terraform 會自動建立：
- Instance: `db-g1-small` (可擴展)
- Region: `asia-southeast1`
- 自動備份: 每日 03:00
- Point-in-time recovery: 啟用

---

## 🖥️ Tauri Client (桌面應用)

### 位置
```
apps/tauri-client/
```

### 安裝與執行

```bash
cd apps/tauri-client
npm install
npm run tauri-dev
```

### 建構發行版

```bash
npm run tauri-build
```

---

## ☁️ GCP 部署 (Terraform)

### 位置
```
terraform/
```

### 設定步驟

1. 複製範例設定檔：
```bash
cp terraform.tfvars.example terraform.tfvars
```

2. 編輯 `terraform.tfvars`：

```hcl
project_id    = "your-gcp-project-id"
region        = "asia-southeast1"
db_password   = "your-secure-db-password"
hf_auth_token = "hf_your_token_here"
secret_key    = "your-jwt-secret-key"
```

3. 部署：

```bash
terraform init
terraform plan
terraform apply
```

### 建立的資源

| 資源 | 名稱 | 說明 |
|-----|------|------|
| Cloud SQL | `meetchi-db` | PostgreSQL 15 |
| Cloud Run | `meetchi-backend` | Backend API |
| Cloud Run | `meetchi-llm` | LLM Service (GPU) |
| Cloud Tasks | `meetchi-summarization-queue` | 摘要任務佇列 |
| Cloud Storage | `{project}-meetchi-audio` | 音訊檔案儲存 |
| Secret Manager | `meetchi-db-password` | 資料庫密碼 |
| Secret Manager | `meetchi-hf-token` | Hugging Face Token |
| Secret Manager | `meetchi-secret-key` | JWT Secret |

---

## 📁 專案結構

```
MeetChi/
├── apps/
│   ├── frontend/          # Next.js Web Dashboard
│   ├── backend/           # FastAPI Backend
│   ├── llm_service/       # Flask LLM Service
│   └── tauri-client/      # Tauri Desktop App
├── terraform/             # GCP Infrastructure
└── docs/                  # Documentation
```

---

## 🔒 安全設定

### 必要的 Secret

| Secret | 用途 | 生成方式 |
|--------|------|---------|
| `NEXTAUTH_SECRET` | NextAuth.js | `openssl rand -hex 32` |
| `secret_key` | JWT 簽名 | `openssl rand -hex 32` |
| `db_password` | 資料庫密碼 | 自行設定強密碼 |
| `GOOGLE_CLIENT_SECRET` | OAuth | Google Cloud Console |
| `HF_TOKEN` | Hugging Face | huggingface.co/settings/tokens |

---

## 🚀 快速開始

### 本地開發（完整流程）

```bash
# 1. Clone repo
git clone https://github.com/jerry88277/MeetChi.git
cd MeetChi

# 2. 啟動資料庫 (Docker)
docker run -d --name meetchi-db \
  -e POSTGRES_USER=meetchi_user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=meetchi \
  -p 5432:5432 \
  postgres:15

# 3. 啟動 Backend
cd apps/backend
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. 啟動 LLM Service (需要 GPU)
cd apps/llm_service
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py

# 5. 啟動 Frontend
cd apps/frontend
npm install && npm run dev

# 6. 啟動 Tauri Client
cd apps/tauri-client
npm install && npm run tauri-dev
```

---

## 📞 連接埠總覽

| 服務 | Port | 說明 |
|-----|------|------|
| Frontend | 3000 | Web Dashboard |
| Backend | 8000 | REST API + WebSocket |
| LLM Service | 8001 | LLM 推論 API |
| PostgreSQL | 5432 | 資料庫 |

---

## 📝 版本資訊

- **文件版本**: 1.0.0
- **最後更新**: 2026-02-05
- **維護者**: MeetChi Team
