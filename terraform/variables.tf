# ============================================================================
# MLOps on GCP — Terraform Variables
# ============================================================================
# All configurable values in one place. Override via terraform.tfvars
# or -var flags.
# ============================================================================

# --- Project & Region ---

variable "project_id" {
  description = "GCP project ID (not project number)"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-central2"
}

variable "zone" {
  description = "GCP zone for zonal resources"
  type        = string
  default     = "europe-central2-a"
}

# --- GKE ---

variable "gke_cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "mlops-cluster"
}

variable "gke_machine_type" {
  description = "Machine type for GKE node pool"
  type        = string
  default     = "e2-standard-2" # 2 vCPU, 8 GB. enough for serving + monitoring
}

variable "gke_min_nodes" {
  description = "Minimum nodes in the node pool"
  type        = number
  default     = 1
}

variable "gke_max_nodes" {
  description = "Maximum nodes in the node pool (autoscaling ceiling)"
  type        = number
  default     = 3
}

variable "gke_disk_size_gb" {
  description = "Boot disk size for GKE nodes in GB"
  type        = number
  default     = 50
}

# --- Artifact Registry ---

variable "docker_repo_name" {
  description = "Name of the Artifact Registry Docker repository"
  type        = string
  default     = "mlops-containers"
}

# --- Storage ---

variable "storage_location" {
  description = "GCS bucket location (multi-region or region)"
  type        = string
  default     = "EU"
}

variable "data_retention_days" {
  description = "Days to keep old pipeline artifacts before cleanup"
  type        = number
  default     = 30
}

# --- Networking ---

variable "network_name" {
  description = "VPC network name"
  type        = string
  default     = "mlops-vpc"
}

variable "subnet_cidr" {
  description = "CIDR range for the subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "pods_cidr" {
  description = "Secondary CIDR range for GKE pods"
  type        = string
  default     = "10.1.0.0/16"
}

variable "services_cidr" {
  description = "Secondary CIDR range for GKE services"
  type        = string
  default     = "10.2.0.0/20"
}

# --- Labels ---

variable "environment" {
  description = "Environment label (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "labels" {
  description = "Common labels applied to all resources"
  type        = map(string)
  default     = {}
}

locals {
  common_labels = merge(
    {
      project     = "mlops-gcp"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.labels
  )
}
