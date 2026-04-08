# ============================================================================
# MLOps on GCP — Main Configuration
# ============================================================================
# Provider config, remote state backend, and GCP API enablement.
#
# FIRST-TIME SETUP:
#   1. Create the state bucket manually (one-time):
#      gcloud storage buckets create gs://your-name-tf-state --location=EU
#      gcloud storage buckets update gs://your-name-tf-state --versioning
#      gcloud storage buckets update gs://your-name-tf-state --update-labels=owner=your_name
#   2. Update the backend block below with your bucket name and prefix.
#   3. Run: terraform init
# ============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

 backend "gcs" {
   bucket = "mlops-proj-tf-state"
   prefix = "mlops-gcp"
 }
}

# --- Providers ---

provider "google" {
  project = var.project_id
  region  = var.region
}

# Kubernetes & Helm providers depend on GKE cluster data
provider "kubernetes" {
  host                   = "https://${google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = "https://${google_container_cluster.primary.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
  }
}

data "google_client_config" "default" {}

# Enable all required APIs before creating resources.
locals {
  required_apis = [
    "aiplatform.googleapis.com",        # Vertex AI
    "container.googleapis.com",         # GKE
    "artifactregistry.googleapis.com",  # Docker image registry
    "storage.googleapis.com",           # Cloud Storage
    "iam.googleapis.com",               # IAM & service accounts
    "compute.googleapis.com",           # Networking, VMs
    "cloudresourcemanager.googleapis.com", # Project metadata
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false 

  timeouts {
    create = "5m"
  }
}
