# ============================================
# Cloud SQL for PostgreSQL
# ============================================
resource "google_sql_database_instance" "meetchi_pg" {
  name             = "meetchi-db-pg"
  database_version = "POSTGRES_15"
  region           = var.region
  
  deletion_protection = false

  settings {
    tier = "db-f1-micro"

    # NOTE: cloudsql.enable_pgvector flag was historically required but is NOT
    # a valid Cloud SQL flag anymore (apply returns 404 invalidFlagName).
    # PostgreSQL 15+ on Cloud SQL has pgvector built-in; just `CREATE EXTENSION
    # vector;` from inside the database. The extension is already created on
    # this instance and used by app/embedding.py for RAG.

    ip_configuration {
      ipv4_enabled = true
    }
  }
}

resource "google_sql_database" "default" {
  name     = "meetchi"
  instance = google_sql_database_instance.meetchi_pg.name
}

resource "random_password" "db_password" {
  length  = 16
  special = false
}

resource "google_sql_user" "default" {
  name     = "postgres"
  instance = google_sql_database_instance.meetchi_pg.name
  password = random_password.db_password.result
}

# ============================================
# Cloud Storage Bucket (for SQLite DB persistence via GCS FUSE)
# Mounts to /mnt/db in Cloud Run — provides durable SQLite storage
# ============================================
resource "google_storage_bucket" "db" {
  name     = "${var.project_id}-meetchi-db"
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = false  # protect DB data

  versioning {
    enabled = true  # keep DB file history for recovery
  }
}


# ============================================
# Cloud Tasks Queue (replaces Celery + Redis)
# ============================================

resource "google_cloud_tasks_queue" "transcription" {
  name     = "meetchi-transcription-queue"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 5
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "3600s"
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 4
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_tasks_queue" "summarization" {
  name     = "meetchi-summarization-queue"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 3
  }

  retry_config {
    max_attempts       = 3
    max_retry_duration = "1800s"
    min_backoff        = "30s"
    max_backoff        = "600s"
    max_doublings      = 3
  }

  depends_on = [google_project_service.apis]
}

# ============================================
# Cloud Storage Bucket (for audio files)
# ============================================

resource "google_storage_bucket" "audio" {
  name     = "${var.project_id}-meetchi-audio"
  location = var.region

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 365 # Keep audio files for 1 year
    }
    action {
      type = "Delete"
    }
  }

  cors {
    origin          = ["*"] # Restrict in production
    method          = ["GET", "POST", "PUT"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# ============================================
# Secret Manager
# ============================================

# db_password secret
resource "google_secret_manager_secret" "db_password" {
  secret_id = "meetchi-db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result

  lifecycle {
    # secret_data 由首次 apply 寫入；後續輪替走 gcloud secrets versions add，
    # 由 GCP 端管理。Terraform 不重寫 (避免重複 destroy/create 切換期失效)。
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "hf_token" {
  secret_id = "meetchi-hf-token"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "hf_token" {
  secret      = google_secret_manager_secret.hf_token.id
  secret_data = var.hf_auth_token

  lifecycle {
    # HF token 輪替走 gcloud secrets versions add (避免 PowerShell stdin
    # 編碼污染 + Terraform var.hf_auth_token 不易維持與 GCP 一致)。
    # gpu-asr 透過 version=latest 自動讀新版本。
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "secret_key" {
  secret_id = "meetchi-secret-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = var.secret_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Gemini API Key for LLM summarization
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "meetchi-gemini-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key

  lifecycle {
    ignore_changes = [secret_data]
  }
}
