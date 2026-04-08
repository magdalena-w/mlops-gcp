# ============================================================================
# GKE Cluster — Standard mode with Workload Identity
# ============================================================================
# Standard (not Autopilot) for more control over node pools, monitoring
# stack, and custom metrics. Workload Identity is enabled cluster-wide
# so pods can assume GCP service accounts without key files.
#
# Cost optimization:
#   - Single node pool with autoscaling (1-3 nodes)
#   - Preemptible/spot nodes for dev (swap to on-demand for prod)
#   - e2-standard-2: enough for serving + Prometheus + Grafana
# ============================================================================

resource "google_container_cluster" "primary" {
  name     = var.gke_cluster_name
  project  = var.project_id
  location = var.zone # Zonal cluster — cheaper than regional for dev

  # We manage node pools separately
  remove_default_node_pool = true
  initial_node_count       = 1

  # VPC-native networking
  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Workload Identity — the secure way to give pods GCP permissions
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Release channel keeps the cluster auto-updated
  release_channel {
    channel = "REGULAR"
  }

  # Logging & monitoring with Google Cloud
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus { enabled = true } # GMP — complements our self-hosted Prometheus
  }

  resource_labels = local.common_labels

  # Deletion protection — disable for dev to allow easy terraform destroy
  deletion_protection = false

  depends_on = [
    google_project_service.apis,
    google_compute_subnetwork.subnet,
  ]
}

# --- Node Pool ---

resource "google_container_node_pool" "primary" {
  name     = "primary-pool"
  project  = var.project_id
  location = var.zone
  cluster  = google_container_cluster.primary.name

  # Autoscaling: scale from min to max based on demand
  autoscaling {
    min_node_count = var.gke_min_nodes
    max_node_count = var.gke_max_nodes
  }

  node_config {
    machine_type = var.gke_machine_type
    disk_size_gb = var.gke_disk_size_gb
    disk_type    = "pd-standard"

    # Use spot VMs for dev — 60-91% cheaper, can be preempted
    # Switch to on-demand (remove this line) for production
    spot = true

    # GCE_METADATA lets pods use the node's default compute SA directly.
    # In production, use GKE_METADATA (Workload Identity) with dedicated SAs.
    # We use GCE_METADATA here due to org policy restrictions on IAM.
    workload_metadata_config {
      mode = "GCE_METADATA"
    }

    # OAuth scopes — with Workload Identity these are the minimum needed
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = local.common_labels

    # Shielded instance — security best practice
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
