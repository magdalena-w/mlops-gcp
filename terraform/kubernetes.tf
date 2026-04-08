# ============================================================================
# Kubernetes Resources — Namespaces & Service Accounts
# ============================================================================
# Create the K8s namespaces and service accounts that later phases
# will deploy into. This keeps namespace management in Terraform
# rather than scattered across kubectl commands.
#
# Currently using the default Compute Engine SA for all workloads.
# In production, this would use Workload Identity with dedicated SAs
# (see iam.tf PRODUCTION UPGRADE PATH).
# ============================================================================

# --- Namespaces ---

resource "kubernetes_namespace" "serving" {
  metadata {
    name   = "serving"
    labels = local.common_labels
  }

  depends_on = [google_container_node_pool.primary]
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name   = "monitoring"
    labels = local.common_labels
  }

  depends_on = [google_container_node_pool.primary]
}

# --- Kubernetes Service Account ---

resource "kubernetes_service_account" "model_server" {
  metadata {
    name      = "model-server"
    namespace = kubernetes_namespace.serving.metadata[0].name
    labels    = local.common_labels

    # PRODUCTION: Add Workload Identity annotation here:
    # annotations = {
    #   "iam.gke.io/gcp-service-account" = "model-server-sa@<PROJECT_ID>.iam.gserviceaccount.com"
    # }
  }
}
