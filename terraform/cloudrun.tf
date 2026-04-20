# ============================================
# Service Account for Cloud Run
# ============================================

resource "google_service_account" "cloudrun" {
  account_id   = "meetchi-cloudrun"
  display_name = "MeetChi Cloud Run Service Account"
}

# Grant necessary permissions
resource "google_project_iam_member" "cloudrun_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

resource "google_project_iam_member" "cloudrun_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

resource "google_project_iam_member" "cloudrun_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

resource "google_project_iam_member" "cloudrun_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

# Gemini API via ADC (Application Default Credentials)
resource "google_project_iam_member" "cloudrun_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

# Cloud Tasks enqueuer (needed for Webhook → Cloud Tasks summarization dispatch)
resource "google_project_iam_member" "cloudrun_cloudtasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.cloudrun.email}"
}

# ============================================
# Cloud Run - Backend API (No GPU)
# ============================================

resource "google_cloud_run_v2_service" "backend" {
  name     = "meetchi-backend"
  location = var.region

  template {
    service_account = google_service_account.cloudrun.email
    timeout         = "3600s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.backend_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg2://postgres:${random_password.db_password.result}@/meetchi?host=/cloudsql/${google_sql_database_instance.meetchi_pg.connection_name}"
      }

      env {
        name  = "CLOUD_TASKS_QUEUE"
        value = "projects/${var.project_id}/locations/${var.region}/queues/meetchi-transcription-queue"
      }


      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.audio.name
      }

      env {
        name  = "GEMINI_MODEL"
        value = "gemini-2.5-flash-lite"
      }

      env {
        name  = "GEMINI_LOCATION"
        value = "us-central1"
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_LOCATION"
        value = var.region
      }

      env {
        name  = "GPU_ASR_SERVICE_URL"
        value = "https://meetchi-gpu-asr-705495828555.asia-southeast1.run.app"
      }

      env {
        name  = "BACKEND_PUBLIC_URL"
        value = "https://meetchi-backend-705495828555.asia-southeast1.run.app"
      }

      env {
        name  = "DISCORD_WEBHOOK_URL"
        value = var.discord_webhook_url
      }

      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }

      # GCS FUSE mount removed completely to prevent SQLite locks
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 30
        failure_threshold = 3
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.meetchi_pg.connection_name]
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_tasks_queue.transcription,
    google_storage_bucket.db,
    google_sql_database_instance.meetchi_pg,
    google_sql_user.default
  ]
}


# ============================================
# NOTE: meetchi-gpu-asr is managed directly via gcloud CLI
# (not via Terraform) due to GPU node_selector provider compatibility.
# Deployed with: gcloud run deploy meetchi-gpu-asr --image ...
# ============================================

resource "google_cloud_run_v2_service_iam_member" "gpu_asr_backend" {
  name     = "meetchi-gpu-asr"
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloudrun.email}"
}



# ============================================
# IAM - Allow unauthenticated access (public API)
# ============================================

resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

