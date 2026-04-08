# ============================================================================
# Cloud Storage — Data, Models, Pipeline Artifacts
# ============================================================================
# Three buckets with distinct purposes and lifecycle policies:
#
#   - data:      Raw and processed datasets
#   - models:    Versioned model artifacts (kept longer)
#   - pipeline:  Vertex AI pipeline intermediate artifacts (auto-cleaned)
#
# Bucket names are globally unique, so we prefix with project_id.
# ============================================================================

resource "google_storage_bucket" "data" {
  name     = "${var.project_id}-mlops-data"
  project  = var.project_id
  location = var.storage_location

  # Prevent accidental deletion of training data
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true # Track dataset versions
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "models" {
  name     = "${var.project_id}-mlops-models"
  project  = var.project_id
  location = var.storage_location

  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true # Critical for model lineage
  }

  # Keep model artifacts for 90 days even after "deletion"
  # (soft delete via versioning)
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5 # Keep last 5 versions of each model
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "pipeline_artifacts" {
  name     = "${var.project_id}-mlops-pipeline-artifacts"
  project  = var.project_id
  location = var.storage_location

  force_destroy = false

  uniform_bucket_level_access = true

  # Auto-cleanup pipeline artifacts — they're reproducible
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = var.data_retention_days
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# --- IAM for bucket access ---
# Managed manually via GCP Console. See iam.tf MANUAL_IAM_SETUP.
