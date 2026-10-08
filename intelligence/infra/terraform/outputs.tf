output "artifact_registry_repository" {
  description = "Artifact Registry repository used for service images."
  value       = google_artifact_registry_repository.images.name
}

output "image_prefix" {
  description = "Prefix to use when tagging the container image."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${var.service_name}"
}

output "openai_secret_name" {
  description = "Secret Manager secret that needs an out-of-band value."
  value       = google_secret_manager_secret.openai_api_key.secret_id
}

output "service_url" {
  description = "Public Cloud Run URL to configure in the dashboard as VITE_NHL_INTELLIGENCE_URL."
  value       = google_cloud_run_v2_service.api.uri
}
