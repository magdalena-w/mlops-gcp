# ============================================================================
# Networking — VPC + Subnet with GKE secondary ranges
# ============================================================================
# VPC-native GKE cluster requires a subnet with secondary IP ranges
# for pods and services. This is the GCP-recommended setup and avoids
# the legacy routes-based networking.
# ============================================================================

resource "google_compute_network" "vpc" {
  name                    = var.network_name
  project                 = var.project_id
  auto_create_subnetworks = false # We manage subnets explicitly

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.network_name}-subnet"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.subnet_cidr

  # Secondary ranges for GKE pods and services (VPC-native)
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  # Enable private Google access so nodes without external IPs
  # can still reach Google APIs (Cloud Storage, Vertex AI, etc.)
  private_ip_google_access = true
}

# --- Firewall: allow internal communication within the VPC ---
resource "google_compute_firewall" "internal" {
  name    = "${var.network_name}-allow-internal"
  project = var.project_id
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = [
    var.subnet_cidr,
    var.pods_cidr,
    var.services_cidr,
  ]
}
