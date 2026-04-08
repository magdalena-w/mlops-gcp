# ============================================================================
# IAM — Service Account Configuration
# ============================================================================
# This project uses the default Compute Engine service account
# (<PROJECT_NUMBER>-compute@developer.gserviceaccount.com) which has
# Editor role and covers all needed permissions: GCS, Artifact Registry,
# Vertex AI, GKE workloads.
#
# This is intentional for a learning environment where org
# policies restrict IAM management. GKE nodes already use this SA via
# the oauth_scopes = ["cloud-platform"] setting in gke.tf.
#
# ============================================================================
# PRODUCTION UPGRADE PATH
# ============================================================================
# In a real environment with full IAM access, replace the default SA
# with dedicated least-privilege service accounts:
#
#   1. vertex-pipeline-sa (Vertex AI User + Storage Object Admin +
#      Artifact Registry Writer)
#
#   2. model-server-sa (Storage Object Viewer only) bound via
#      Workload Identity to a K8s SA in the serving namespace
#
#   3. GitHub Actions authenticated via Workload Identity Federation
#      (OIDC pool + provider) — zero long-lived keys
#
# This follows the principle of least privilege: each component only
# gets the permissions it actually needs, and no service account keys
# are ever created.
# ============================================================================

# Fetch the default compute SA for reference in other modules
data "google_compute_default_service_account" "default" {
  project = var.project_id
}
