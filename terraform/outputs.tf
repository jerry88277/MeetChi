# Cloud Run Backend URL
output "backend_url" {
  description = "URL of the Backend Cloud Run service"
  value       = google_cloud_run_v2_service.backend.uri
}

# ── IAP + Load Balancer ───────────────────────────────────────────────────────

output "lb_static_ip" {
  description = "Global LB Static IP — 提供此 IP 給 IT 設定 DNS A record (meetchi.chimei.com.tw → <this IP>)"
  value       = google_compute_global_address.lb_ip.address
}

output "iap_client_id" {
  description = "IAP OAuth Client ID（前端 NEXT_AUTH 或 gcloud IAP proxy 設定用）"
  value       = google_iap_client.meetchi.client_id
  sensitive   = false
}

output "meetchi_url" {
  description = "MeetChi 對外 URL（DNS + SSL 生效後可訪問）"
  value       = "https://${var.custom_domain}"
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
