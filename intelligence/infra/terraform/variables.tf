variable "project_id" {
  description = "Google Cloud project ID that will host NHL Intelligence."
  type        = string
}

variable "region" {
  description = "Google Cloud region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-east4"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "nhl-intelligence"
}

variable "image" {
  description = "Immutable Artifact Registry image reference to deploy, preferably tagged with a commit SHA."
  type        = string
}

variable "dashboard_api_url" {
  description = "Read-only NHL Dashboard API base URL."
  type        = string
  default     = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io"
}

variable "allowed_origins" {
  description = "Comma-separated browser origins allowed by the API CORS policy."
  type        = string
  default     = "https://ashy-sky-01e4eba1e.7.azurestaticapps.net"
}

variable "openai_model" {
  description = "OpenAI model used by the Intelligence service."
  type        = string
  default     = "gpt-5.6-luna"
}

variable "openai_secret_id" {
  description = "Secret Manager secret ID. The secret value is added outside Terraform to keep it out of state."
  type        = string
  default     = "nhl-intelligence-openai-api-key"
}

variable "max_instances" {
  description = "Maximum Cloud Run instances, limiting accidental spend."
  type        = number
  default     = 2

  validation {
    condition     = var.max_instances >= 1 && var.max_instances <= 10
    error_message = "max_instances must be between 1 and 10."
  }
}
