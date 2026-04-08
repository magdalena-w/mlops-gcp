# ============================================================================
# Artifact Registry — Docker Container Repository
# ============================================================================
# Single Docker repository for all container images:
#   - Pipeline step containers (data ingestion, training, evaluation)
#   - Model serving container (FastAPI)
#
# Images are tagged with git SHA for traceability.
# ============================================================================

resource "google_artifact_registry_repository" "docker" {
  repository_id = var.docker_repo_name
  project       = var.project_id
  location      = var.region
  format        = "DOCKER"
  description   = "Container images for MLOps pipeline and serving"

  # Auto-cleanup old images to control storage costs
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}
