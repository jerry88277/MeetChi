# ============================================
# Cloud SQL — REMOVED (migrated to SQLite on GCS FUSE)
# Instance meetchi-db was deleted on 2026-02-11
# ============================================

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

# db_password secret — REMOVED (Cloud SQL deleted)

resource "google_secret_manager_secret" "hf_token" {
  secret_id = "meetchi-hf-token"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "hf_token" {
  secret      = google_secret_manager_secret.hf_token.id
  secret_data = var.hf_auth_token
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
}
