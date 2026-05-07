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
# Cloud Run - GPU ASR Service (L4 GPU)
# ============================================
# Replaces the previous "manage via gcloud CLI" workaround.
# Provider hashicorp/google 5.x does NOT support template.node_selector;
# GPU type (nvidia-l4) is set via gcloud/yaml on the live service and the
# accelerator change is excluded from this resource's plan via
# lifecycle.ignore_changes (covered by the broad annotations + client* ignore).
#
# IMPORTANT — first-time IaC adoption procedure:
#   1) Verify live config matches the resource block below:
#        gcloud run services describe meetchi-gpu-asr --region asia-southeast1
#   2) Import the live service WITHOUT recreating it:
#        terraform import google_cloud_run_v2_service.gpu_asr \
#          projects/${PROJECT_ID}/locations/${REGION}/services/meetchi-gpu-asr
#   3) Run `terraform plan` and verify it shows 0 changes for this resource.
#      If it shows changes, ALIGN the HCL to the live config — do NOT apply
#      changes blindly. GPU services have ~90s cold-start during recreation.
#   4) Image tag is intentionally `lifecycle.ignore_changes` so that
#      gcloud / cloudbuild deploys don't trigger Terraform drift. Image
#      lifecycle is owned by cloudbuild-gpu-asr.yaml.
#
# Live config snapshot (2026-04-22, revision 00038):
#   image: meetchi-gpu-asr:v15-community1
#   memory 32Gi, cpu 8, gpu 1 (nvidia-l4)
#   env: DIARIZATION_MODEL=community-1, HF_AUTH_TOKEN/HF_TOKEN (Secret Manager)
#   volume: /mnt/gcs -> ${audio bucket} via GCS Fuse
#   timeout 3600s, concurrency 1, min 0 max 1, CPU always allocated
resource "google_cloud_run_v2_service" "gpu_asr" {
  provider     = google-beta
  name         = "meetchi-gpu-asr"
  location     = var.region
  launch_stage = "GA"

  template {
    service_account = google_service_account.cloudrun.email
    timeout         = "3600s"

    scaling {
      max_instance_count = 1
    }

    # GPU services must keep CPU always allocated; throttling causes the
    # accelerator driver context to die between requests.
    annotations = {
      "run.googleapis.com/cpu-throttling"                = "false"
      "run.googleapis.com/startup-cpu-boost"             = "true"
      "run.googleapis.com/gpu-zonal-redundancy-disabled" = "true"
    }

    # GPU accelerator (nvidia-l4) is configured via the live service and
    # NOT manageable from hashicorp/google v5.x (no node_selector block in
    # google_cloud_run_v2_service). Listed in lifecycle.ignore_changes so
    # Terraform won't try to remove it on plan. To upgrade GPU type, do it
    # via gcloud or upgrade provider to google v6+.

    containers {
      name  = "meetchi-gpu-asr-1"
      image = var.gpu_asr_image
      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu              = "8000m"
          memory           = "32Gi"
          "nvidia.com/gpu" = "1"
        }
        startup_cpu_boost = true
      }

      # Env order MUST match the live service to avoid spurious diffs
      # (Terraform compares env blocks positionally).
      # HF tokens — sourced from Secret Manager. Two duplicate vars because
      # different libraries (huggingface_hub vs pyannote) read different names.
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
        name = "HF_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.hf_token.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "DIARIZATION_MODEL"
        value = "community-1"
      }

      volume_mounts {
        name       = "gcs-data"
        mount_path = "/mnt/gcs"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 30
        period_seconds        = 20
        timeout_seconds       = 10
        failure_threshold     = 10
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 60
        timeout_seconds   = 1
        failure_threshold = 3
      }
    }

    volumes {
      name = "gcs-data"
      gcs {
        bucket    = google_storage_bucket.audio.name
        read_only = false
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  lifecycle {
    # Image lifecycle is owned by cloudbuild-gpu-asr.yaml + manual gcloud deploys.
    # Traffic split (pinned revision vs LATEST + community1 tag) is owned by
    # the cloudbuild deploy step and gcloud — Terraform must not fight with it.
    # Annotations may include runtime-managed labels (deploy-version etc.).
    ignore_changes = [
      template[0].containers[0].image,
      template[0].annotations,
      traffic,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket.audio,
    google_secret_manager_secret_version.hf_token,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "gpu_asr_backend" {
  name     = google_cloud_run_v2_service.gpu_asr.name
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

