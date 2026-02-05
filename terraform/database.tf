# ============================================
# Cloud SQL PostgreSQL Instance
# ============================================

resource "google_sql_database_instance" "main" {
  name             = var.db_instance_name
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = "db-g1-small" # Start small, scale as needed
    
    # High availability for production
    availability_type = "ZONAL" # Change to REGIONAL for HA
    
    disk_size = 20
    disk_type = "PD_SSD"
    
    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7
      }
    }
    
    ip_configuration {
      ipv4_enabled    = true
      private_network = null # Add VPC for private access
      
      # Allow Cloud Run to connect
      authorized_networks {
        name  = "allow-all" # Restrict in production
        value = "0.0.0.0/0"
      }
    }
    
    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }

  deletion_protection = true
  
  depends_on = [google_project_service.apis]
}

# Database
resource "google_sql_database" "meetchi" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

# Database User
resource "google_sql_user" "app_user" {
  name     = var.db_user
  instance = google_sql_database_instance.main.name
  password = var.db_password
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

resource "google_secret_manager_secret" "db_password" {
  secret_id = "meetchi-db-password"
  
  replication {
    auto {}
  }
  
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
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
