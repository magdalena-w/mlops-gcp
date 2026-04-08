# ============================================================================
# Outputs — Values needed by pipelines, serving, and CI/CD
# ============================================================================
# These outputs serve two purposes:
#   1. Referenced by other Terraform configs or scripts
#   2. Used as GitHub Actions secrets / environment variables
#
# After `terraform apply`, run:
#   terraform output -json > tf-outputs.json
# to capture all values for downstream use.
# ============================================================================

# --- GKE ---

output "gke_cluster_name" {
  description = "GKE cluster name for kubectl/gcloud"
  value       = google_container_cluster.primary.name
}

output "gke_cluster_endpoint" {
  description = "GKE cluster API endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "gke_cluster_location" {
  description = "GKE cluster zone/region"
  value       = google_container_cluster.primary.location
}

# --- Artifact Registry ---

output "docker_registry_url" {
  description = "Full Artifact Registry URL for docker push/pull"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

# --- Storage ---

output "data_bucket" {
  description = "GCS bucket for datasets"
  value       = google_storage_bucket.data.name
}

output "models_bucket" {
  description = "GCS bucket for model artifacts"
  value       = google_storage_bucket.models.name
}

output "pipeline_artifacts_bucket" {
  description = "GCS bucket for Vertex AI pipeline artifacts"
  value       = google_storage_bucket.pipeline_artifacts.name
}

# --- IAM ---

output "default_compute_sa_email" {
  description = "Default Compute Engine SA used by all workloads"
  value       = data.google_compute_default_service_account.default.email
}

# --- Convenience: connection command ---

output "connect_command" {
  description = "Run this to configure kubectl"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --zone ${var.zone} --project ${var.project_id}"
}
