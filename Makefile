# ============================================================================
# Single entry point for all operations. Uses terraform outputs to
# avoid hardcoding project-specific values.
#
# Usage:
#   make tf-apply      # Provision infrastructure
#   make upload-data   # Upload training dataset to GCS
#   make build-serving # Build model server container
#   make deploy        # Deploy to GKE
# ============================================================================

# --- Dynamic config from Terraform outputs ---
PYTHON         := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)
PROJECT_ID     := $(shell cd terraform && terraform output -raw gke_cluster_name 2>/dev/null | head -1 && cd ..)
REGION         := $(shell cd terraform && terraform output -raw gke_cluster_location 2>/dev/null | head -1 && cd ..)
REGISTRY       := $(shell cd terraform && terraform output -raw docker_registry_url 2>/dev/null)
DATA_BUCKET    := $(shell cd terraform && terraform output -raw data_bucket 2>/dev/null)
MODELS_BUCKET  := $(shell cd terraform && terraform output -raw models_bucket 2>/dev/null)
PIPELINE_BUCKET := $(shell cd terraform && terraform output -raw pipeline_artifacts_bucket 2>/dev/null)
CLUSTER_NAME   := $(shell cd terraform && terraform output -raw gke_cluster_name 2>/dev/null)
CLUSTER_ZONE   := $(shell cd terraform && terraform output -raw gke_cluster_location 2>/dev/null)

# Image tagging — git SHA for traceability, "latest" as convenience
GIT_SHA        := $(shell git rev-parse --short HEAD 2>/dev/null || echo "dev")
TAG            ?= $(GIT_SHA)

# ============================================================================
# Infrastructure
# ============================================================================

.PHONY: tf-init tf-plan tf-apply tf-destroy tf-output

tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply

tf-destroy:
	cd terraform && terraform destroy

tf-output:
	cd terraform && terraform output

# ============================================================================
# Cluster Access
# ============================================================================

.PHONY: cluster-auth cluster-info

cluster-auth:
	gcloud container clusters get-credentials $(CLUSTER_NAME) \
		--zone $(CLUSTER_ZONE)

cluster-info:
	@echo "--- Nodes ---"
	@kubectl get nodes
	@echo ""
	@echo "--- Namespaces ---"
	@kubectl get namespaces serving monitoring
	@echo ""
	@echo "--- Serving Namespace ---"
	@kubectl get all -n serving
	@echo ""
	@echo "--- Monitoring Namespace ---"
	@kubectl get all -n monitoring

# ============================================================================
# Data
# ============================================================================

.PHONY: generate-data upload-data list-data

generate-data:
	@echo "Generating Wine dataset..."
	$(PYTHON) scripts/generate_dataset.py
	@echo "Done: data/wine_data.csv"

upload-data: generate-data
	@echo "Uploading to gs://$(DATA_BUCKET)/raw/..."
	gcloud storage cp data/wine_data.csv gs://$(DATA_BUCKET)/raw/wine_data.csv
	@echo "Done."

list-data:
	gcloud storage ls gs://$(DATA_BUCKET)/raw/

# ============================================================================
# Docker — Pipeline & Serving Containers
# ============================================================================

.PHONY: docker-auth build-serving push-serving build-all push-all

docker-auth:
	gcloud auth configure-docker $(shell echo $(REGISTRY) | cut -d'/' -f1)

build-serving:
	docker build --platform linux/amd64 -t $(REGISTRY)/model-server:$(TAG) serving/
	docker tag $(REGISTRY)/model-server:$(TAG) $(REGISTRY)/model-server:latest

push-serving: docker-auth build-serving
	docker push $(REGISTRY)/model-server:$(TAG)
	docker push $(REGISTRY)/model-server:latest

build-all: build-serving

push-all: push-serving

# ============================================================================
# Pipeline
# ============================================================================

.PHONY: run-pipeline

run-pipeline:
	$(PYTHON) pipelines/run.py \
		--data-bucket $(DATA_BUCKET) \
		--model-bucket $(MODELS_BUCKET) \
		--pipeline-bucket $(PIPELINE_BUCKET)

# ============================================================================
# Serving — Local & GKE
# ============================================================================

.PHONY: run-local deploy

run-local:
	cd serving && uvicorn app:app --reload --port 8080

deploy: push-serving
	kubectl set image deployment/wine-classifier \
		model-server=$(REGISTRY)/model-server:$(TAG) \
		-n serving

# ============================================================================
# Monitoring
# ============================================================================

.PHONY: port-forward-grafana port-forward-prometheus

port-forward-grafana:
	@echo "Grafana available at http://localhost:3000"
	kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring

port-forward-prometheus:
	@echo "Prometheus available at http://localhost:9090"
	kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring

# ============================================================================
# Testing & Linting
# ============================================================================

.PHONY: test lint fmt

test:
	pytest tests/ -v

lint:
	ruff check .
	cd terraform && terraform fmt -check

fmt:
	ruff format .
	cd terraform && terraform fmt

# ============================================================================
# Cleanup
# ============================================================================

.PHONY: clean

clean:
	rm -rf data/*.csv
	rm -rf pipelines/compiled/*.json
	find . -type d -name __pycache__ -exec rm -rf {} +
	@echo "Cleaned local artifacts. Run 'make tf-destroy' to tear down GCP resources."

# ============================================================================
# Help
# ============================================================================

.PHONY: help

help:
	@echo "MLOps on GCP — Available targets:"
	@echo ""
	@echo "  Infrastructure:"
	@echo "    tf-init          Initialize Terraform"
	@echo "    tf-plan          Preview infrastructure changes"
	@echo "    tf-apply         Apply infrastructure changes"
	@echo "    tf-destroy       Tear down all GCP resources"
	@echo "    tf-output        Show Terraform outputs"
	@echo ""
	@echo "  Cluster:"
	@echo "    cluster-auth     Configure kubectl credentials"
	@echo "    cluster-info     Show cluster status"
	@echo ""
	@echo "  Data:"
	@echo "    generate-data    Generate Wine dataset CSV"
	@echo "    upload-data      Generate + upload dataset to GCS"
	@echo "    list-data        List files in data bucket"
	@echo ""
	@echo "  Docker:"
	@echo "    build-serving    Build model server image"
	@echo "    push-serving     Build + push model server image"
	@echo ""
	@echo "  Pipeline:"
	@echo "    run-pipeline     Trigger Vertex AI training pipeline"
	@echo ""
	@echo "  Serving:"
	@echo "    run-local        Run model server locally"
	@echo "    deploy           Deploy model server to GKE"
	@echo ""
	@echo "  Monitoring:"
	@echo "    port-forward-grafana     Access Grafana locally"
	@echo "    port-forward-prometheus  Access Prometheus locally"
	@echo ""
	@echo "  Dev:"
	@echo "    test             Run tests"
	@echo "    lint             Check code formatting"
	@echo "    fmt              Auto-format code"
	@echo "    clean            Remove local artifacts"