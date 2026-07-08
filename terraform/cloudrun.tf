# ============================================
# ⚠️ DRIFT NOTICE (2026-07-08)
# 目前線上 meetchi-backend / meetchi-frontend / meetchi-gpu-asr 服務**並非**由此
# tfstate 管理（`terraform state list` 無這些資源），且線上 env 遠多於此檔（AUTH_SECRET、
# ADMIN_EMAILS、SMTP_*、GPU_* 等由 gcloud 增量設定）。因此**請勿**直接 `terraform apply`
# 本檔——會以不完整的 env 覆蓋線上服務造成中斷。此檔目前作為 Source-of-Truth 文件同步；
# 環境變更以 `gcloud run services update --update-env-vars`（增量、非 --set-*）套用，
# 並回填此檔。完整 terraform import/reconcile 為另案 remediation（見 devlog 2026-07-08）。
# ============================================

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
        value = "https://meetchi-gpu-asr-atro34poxq-as.a.run.app"
      }

      env {
        name  = "BACKEND_PUBLIC_URL"
        value = "https://meetchi-backend-315688033208.asia-southeast1.run.app"
      }

      # 2026-07-08 安全加固（UAT）：關閉「未認證即回 mock admin」的漏洞。
      # AUTH_REQUIRED=true → get_current_user 強制驗證 token（前端已送 UAT HS256
      # token，AUTH_SECRET 已設可驗）。AUTH_ALLOWED_DOMAIN 限制正式 OAuth 登入網域
      # （UAT token 仍 bypass 供測試）。CALLBACK_AUTH_REQUIRED=true 啟用 GPU 回呼
      # 的 OIDC 驗證，杜絕偽造 ASR 結果寫入。
      # 註：實際生效以 gcloud --update-env-vars 增量套用（現行服務非由此 tfstate
      # 管理，見檔尾 DRIFT 說明）；本區塊為 Source-of-Truth 同步。
      env {
        name  = "AUTH_REQUIRED"
        value = "true"
      }

      env {
        name  = "AUTH_ALLOWED_DOMAIN"
        value = "mail.chimei.com.tw"
      }

      # CALLBACK_AUTH_REQUIRED：GPU 回呼 OIDC 驗證開關。程式碼已就緒（robust：
      # 驗 Google 簽章 + aud/SA email 比對），但**尚未經真實短音檔上傳實測**，
      # 故暫設 false（enforcement off）。實測通過後改 true。
      env {
        name  = "CALLBACK_AUTH_REQUIRED"
        value = "false"
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

  lifecycle {
    # Image lifecycle is owned by cloudbuild-backend.yaml + manual gcloud
    # deploys; HCL var.backend_image is a default for first-time bootstrap
    # only. Do NOT let Terraform downgrade the live image to whatever happens
    # to be in HCL/var.
    # Env order drift between HCL and live (positional comparison) creates
    # false diffs whenever Cloud Run reorders env vars; ignore template-level
    # changes including ad-hoc env additions like _FORCE_REVISION_TS.
    # client / client_version are gcloud-stamped metadata Terraform can't
    # manage.
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].env,
      client,
      client_version,
    ]
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
# ============================================
# GPU ASR — Deployed via gcloud CLI (NOT Terraform)
# ============================================
# The hashicorp/google v5.x provider does not support the
# gpu_zonal_redundancy_disabled property, and the Cloud Run v2 API
# rejects run.googleapis.com/gpu-zonal-redundancy-disabled as a
# service-level annotation. Deploy via gcloud CLI instead.
#
# resource "google_cloud_run_v2_service" "gpu_asr" {
#   provider     = google-beta
#   name         = "meetchi-gpu-asr"
#   location     = var.region
#   launch_stage = "GA"
#
#   annotations = {
#     "run.googleapis.com/gpu-zonal-redundancy-disabled" = "true"
#   }
#
#   template {
#     service_account = google_service_account.cloudrun.email
#     timeout         = "3600s"
#
#     scaling {
#       max_instance_count = 1
#     }
#
#     annotations = {
#       "run.googleapis.com/cpu-throttling"    = "false"
#       "run.googleapis.com/startup-cpu-boost" = "true"
#     }
#
#     containers {
#       name  = "meetchi-gpu-asr-1"
#       image = var.gpu_asr_image
#       ...
#     }
#
#     volumes {
#       name = "gcs-data"
#       gcs {
#         bucket    = google_storage_bucket.audio.name
#         read_only = false
#       }
#     }
#   }
#
#   traffic {
#     percent = 100
#     type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
#   }
#
#   lifecycle { ... }
#   depends_on = [ ... ]
# }
#
# resource "google_cloud_run_v2_service_iam_member" "gpu_asr_backend" {
#   name     = google_cloud_run_v2_service.gpu_asr.name
#   location = var.region
#   role     = "roles/run.invoker"
#   member   = "serviceAccount:${google_service_account.cloudrun.email}"
# }



# ============================================
# Cloud Run - Frontend (Next.js, No GPU)
# ============================================
# 2026-05-25 (P0 IaC audit)：補上 meetchi-frontend 進 IaC 管理。
# 之前純 gcloud 手動 deploy，沒 IaC = 災難恢復找不到 config 範本。
#
# IMPORTANT — first-time IaC adoption procedure:
#   1) 確認 live 與 HCL 對齊:
#        gcloud run services describe meetchi-frontend --region asia-southeast1
#   2) Import 既有服務（避免 plan 嘗試重建造成 downtime）:
#        terraform import google_cloud_run_v2_service.frontend \
#          projects/${PROJECT_ID}/locations/${REGION}/services/meetchi-frontend
#   3) terraform plan 必須 0 changes 才 apply
#
# Image lifecycle owned by apps/frontend/cloudbuild-frontend.yaml + manual
# gcloud deploys. NEXT_PUBLIC_API_URL 是 build-time bundle 進去（見 cloudbuild
# 內 --build-arg），所以這裡不需要 runtime env。

resource "google_cloud_run_v2_service" "frontend" {
  name     = "meetchi-frontend"
  location = var.region

  template {
    # Changed to managed cloudrun service account to avoid 'actAs' permission denial on the default compute SA
    service_account = google_service_account.cloudrun.email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 20
    }

    containers {
      image = var.frontend_image

      ports {
        container_port = 3000
      }

      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
        # 2026-05-25 align-live：保留 live 既有設定避免 apply 後成本上升 +
        # 冷啟動變慢
        cpu_idle          = true # request 才計費（非 always-on）
        startup_cpu_boost = true # 加速冷啟動
      }

      # NEXT_PUBLIC_API_URL 是 build-time，不在 runtime env
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  lifecycle {
    # Image lifecycle owned by cloudbuild-frontend.yaml + manual gcloud
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].env,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.apis,
  ]
}

# ============================================
# Cloud Run Job - DB Migrate (Alembic)
# ============================================
# 2026-05-25 (P0 IaC audit)：補上 db-migrate-v19 job 進 IaC。
# 之前 gcloud 手動建 → image / cmd / cloudsql connector 散落 console。
#
# 用 backend image 因為含 alembic + app code；service account = meetchi-cloudrun
# 才能透過 Cloud SQL Auth Proxy 連 meetchi-db-pg。
#
# IMPORTANT — first-time IaC adoption:
#   terraform import google_cloud_run_v2_job.db_migrate \
#     projects/${PROJECT_ID}/locations/${REGION}/jobs/db-migrate-v19

resource "google_cloud_run_v2_job" "db_migrate" {
  name     = "db-migrate-v19"
  location = var.region

  template {
    template {
      service_account = google_service_account.cloudrun.email

      containers {
        image   = var.backend_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://postgres:${random_password.db_password.result}@/meetchi?host=/cloudsql/${google_sql_database_instance.meetchi_pg.connection_name}"
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
  }

  lifecycle {
    # Image 對齊 backend image lifecycle（cloudbuild + manual deploy）
    # 2026-05-25 align-live：env 也加進 ignore_changes，與 backend resource 一致。
    # DATABASE_URL 內含 password，HCL 的 random_password.db_password.result 與
    # live 既有 hardcoded password 是 sensitive 比較副作用（值可能相同），但
    # apply 風險高（萬一不同會讓 migrate 連不上 DB）→ 改 ignore，由 manual
    # gcloud 管 env 內容。
    ignore_changes = [
      template[0].template[0].containers[0].image,
      template[0].template[0].containers[0].env,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_sql_database_instance.meetchi_pg,
    google_sql_user.default,
  ]
}

# ============================================
# IAM - Allow unauthenticated access (public API)
# Commented out due to GCP Org Policy constraints/iam.managed.allowedPolicyMembers
# which prohibits public access (allUsers invoker).
# ============================================

# resource "google_cloud_run_v2_service_iam_member" "backend_public" {
#   name     = google_cloud_run_v2_service.backend.name
#   location = var.region
#   role     = "roles/run.invoker"
#   member   = "allUsers"
# }

# resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
#   name     = google_cloud_run_v2_service.frontend.name
#   location = var.region
#   role     = "roles/run.invoker"
#   member   = "allUsers"
# }

