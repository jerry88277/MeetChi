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
variable "db_instance_name" {
  description = "Cloud SQL instance name"
  type        = string
  default     = "meetchi-db"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "MeetChi"
}

variable "db_user" {
  description = "Database username"
  type        = string
  default     = "meetchi_app"
}

variable "db_password" {
  description = "Database password (use Secret Manager in production)"
  type        = string
  sensitive   = true
}

# Cloud Run Configuration
variable "backend_image" {
  description = "Backend Docker image URL"
  type        = string
  default     = "gcr.io/PROJECT_ID/meetchi-backend:latest"
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
