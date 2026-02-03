# Cloud Run Backend URL
output "backend_url" {
  description = "URL of the Backend Cloud Run service"
  value       = google_cloud_run_v2_service.backend.uri
}

# Cloud Run LLM GPU URL
output "llm_service_url" {
  description = "URL of the LLM GPU Cloud Run service"
  value       = google_cloud_run_v2_service.llm_gpu.uri
}

# Cloud SQL Connection
output "database_connection" {
  description = "Cloud SQL connection string"
  value       = "postgresql://${var.db_user}:****@${google_sql_database_instance.main.public_ip_address}:5432/${var.db_name}"
  sensitive   = false
}

output "database_instance_name" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.main.connection_name
}

# Redis
output "redis_host" {
  description = "Redis host for Celery"
  value       = google_redis_instance.celery.host
}

# Storage
output "audio_bucket" {
  description = "GCS bucket for audio files"
  value       = google_storage_bucket.audio.name
}

# Region Info
output "deployment_region" {
  description = "Deployment region (GPU-enabled)"
  value       = var.region
}

output "gpu_quota_info" {
  description = "GPU quota application instructions"
  value       = <<-EOT
    ============================================================
    GPU QUOTA APPLICATION INSTRUCTIONS
    ============================================================
    
    Cloud Run GPU is deployed in: ${var.region}
    (Note: asia-east1/Taiwan does NOT support Cloud Run GPU)
    
    To request GPU quota increase:
    
    1. Go to: https://console.cloud.google.com/iam-admin/quotas
    2. Filter by: "Service: Cloud Run Admin API"
    3. Search for: "NvidiaL4GpuAllocPerProjectRegion"
    4. Select region: ${var.region}
    5. Click "Edit Quotas" → Request increase
    
    Initial quota: 3 GPUs (auto-granted on first deployment)
    Recommended quota: 6-10 GPUs for production
    
    Processing time: ~2 business days
    ============================================================
  EOT
}
