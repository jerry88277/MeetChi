# GCP Project Configuration
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region for Cloud Run GPU (must support L4)"
  type        = string
  default     = "asia-southeast1" # Singapore - closest GPU-supported region to Taiwan
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "asia-southeast1-b"
}

# Database Configuration
variable "db_password" {
  description = "Cloud SQL database password"
  type        = string
  sensitive   = true
  default     = ""
}

# Cloud Run Configuration
variable "backend_image" {
  description = "Backend Docker image URL"
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-backend@sha256:42b849f8078a2c1cd4634a19a221028f6af7673c0a4d5cba9d0a4de02652f6d5"
}

variable "gpu_asr_image" {
  description = "GPU ASR Service Docker image URL"
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/project-51769b5e-7f0f-4a2f-80c/meetchi/meetchi-gpu-asr@sha256:4a74a40ff6f510f54eae8116d89d13a41d5b1b7e85e4c0bb2ca461594d4cb4ad"
}

variable "llm_service_image" {
  description = "LLM Service Docker image URL"
  type        = string
  default     = "gcr.io/PROJECT_ID/meetchi-llm:latest"
}

# GPU Configuration
variable "gpu_enabled" {
  description = "Enable GPU for LLM/ASR services"
  type        = bool
  default     = true
}

variable "gpu_type" {
  description = "GPU type for Cloud Run"
  type        = string
  default     = "nvidia-l4"
}

# Scaling Configuration
variable "min_instances" {
  description = "Minimum instances for Cloud Run"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum instances for Cloud Run"
  type        = number
  default     = 3
}

# Secrets
variable "hf_auth_token" {
  description = "Hugging Face API token for pyannote/whisper"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "JWT Secret Key"
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Google Gemini API Key for LLM summarization"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gpu_asr_service_url" {
  description = "URL for the GPU ASR Cloud Run service (used by backend to call ASR)"
  type        = string
  default     = ""
}
