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

# Cloud SQL outputs — REMOVED (migrated to SQLite on GCS FUSE)

# Cloud Tasks Queues
output "cloud_tasks_transcription_queue" {
  description = "Cloud Tasks queue for transcription tasks"
  value       = google_cloud_tasks_queue.transcription.name
}

output "cloud_tasks_summarization_queue" {
  description = "Cloud Tasks queue for summarization tasks"
  value       = google_cloud_tasks_queue.summarization.name
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
