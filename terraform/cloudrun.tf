# ============================================
# Service Account for Cloud Run
# ============================================

resource "google_service_account" "cloudrun" {
  account_id   = "meetchi-cloudrun"
  display_name = "MeetChi Cloud Run Service Account"
}

# Grant necessary permissions
resource "google_project_iam_member" "cloudrun_sql" {
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

# ============================================
# Cloud Run - Backend API (No GPU)
# ============================================

resource "google_cloud_run_v2_service" "backend" {
  name     = "meetchi-backend"
  location = var.region

  template {
    service_account = google_service_account.cloudrun.email

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
        value = "postgresql://${var.db_user}:${var.db_password}@${google_sql_database_instance.main.public_ip_address}:5432/${var.db_name}"
      }

      env {
        name  = "CLOUD_TASKS_QUEUE"
        value = "projects/${var.project_id}/locations/${var.region}/queues/meetchi-transcription-queue"
      }

      env {
        name  = "LLM_SERVICE_URL"
        value = google_cloud_run_v2_service.llm_gpu.uri
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.audio.name
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
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.apis,
    google_sql_database_instance.main,
    google_cloud_tasks_queue.transcription,
  ]
}

# ============================================
# Cloud Run - LLM/ASR Service (CPU Version - GPU requires quota)
# Apply for GPU quota at: https://console.cloud.google.com/iam-admin/quotas
# Search: NvidiaL4GpuAllocPerProjectRegion, Region: asia-southeast1
# ============================================

resource "google_cloud_run_v2_service" "llm_gpu" {
  # CPU-only for Terraform deployment, GPU enabled via gcloud CLI separately
  name     = "meetchi-llm-gpu"
  location = var.region

  template {
    service_account = google_service_account.cloudrun.email

    scaling {
      min_instance_count = 0 # Scale to zero when idle
      max_instance_count = 1
    }

    # CPU-only resources for initial deployment
    # GPU will be added via: gcloud run services update meetchi-llm-gpu --gpu=1 --gpu-type=nvidia-l4 --no-gpu-zonal-redundancy
    containers {
      image = var.llm_service_image

      ports {
        container_port = 5000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "8Gi"
        }
      }


      env {
        name = "HF_AUTH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.hf_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "CUDA_VISIBLE_DEVICES"
        value = "0"
      }

      env {
        name  = "MODEL_NAME"
        value = "MediaTek-Research/Breeze-7B-Instruct-v1_0"
      }

      env {
        name  = "GCS_MODELS_PATH"
        value = "gs://${var.project_id}-meetchi-audio/models"
      }

      # Gemini API Configuration
      env {
        name  = "USE_GEMINI"
        value = "true"
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GEMINI_MODEL"
        value = "gemini-2.5-flash-lite-preview-06-17"
      }

      # Longer startup for model loading
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 60
        period_seconds        = 30
        timeout_seconds       = 10
        failure_threshold     = 10
      }
    }

    # Cold start timeout (model loading can take time)
    timeout = "900s"
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [google_project_service.apis]
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

# LLM service is internal only (called by backend)
resource "google_cloud_run_v2_service_iam_member" "llm_internal" {
  name     = google_cloud_run_v2_service.llm_gpu.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloudrun.email}"
}
