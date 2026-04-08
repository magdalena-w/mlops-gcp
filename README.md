# MLOps on GCP — Wine Classifier

End-to-end ML infrastructure on Google Cloud Platform: training pipeline, production serving, monitoring, drift detection, and CI/CD. Fully Terraformed, push-to-deploy via GitHub Actions.

**The goal isn't the model — it's the infrastructure around it.** A RandomForest on the Wine dataset is trivial; the production plumbing is what matters.

---

## What this demonstrates

- **Vertex AI Pipeline orchestration** with KFP v2 (typed artifacts, conditional registration, component containerization)
- **Model versioning and lineage** — every model links back to its training data, metrics, and git SHA
- **Quality gating** — models below the accuracy threshold are rejected at pipeline time, never reach production
- **GKE serving** with FastAPI, init-container model loading, HPA autoscaling, and Prometheus metrics
- **Drift detection** — feature baselines captured during training, compared against live traffic via a CronJob that pushes z-scores to Prometheus Pushgateway
- **Full observability stack** — `kube-prometheus-stack`, custom Grafana dashboards, PodMonitor auto-discovery
- **CI/CD via GitHub Actions** — push-to-retrain on `pipelines/` changes, push-to-deploy on `serving/` changes
- **Infrastructure-as-Code** — everything Terraformed, reproducible from zero, costs nothing when torn down
- **Cost-aware design** — spot nodes, lifecycle policies, zonal cluster, bucket retention rules

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Actions                                 │
│  ┌─────────────────────┐                  ┌────────────────────────────┐   │
│  │  retrain.yml        │                  │  deploy.yml                │   │
│  │  (on pipelines/**)  │                  │  (on serving/**)           │   │
│  └──────────┬──────────┘                  └──────────┬─────────────────┘   │
└─────────────┼──────────────────────────────────────────┼──────────────────┘
              │                                          │
              │  Submit pipeline                         │  Build, push, deploy
              ▼                                          ▼
   ┌──────────────────────┐                   ┌──────────────────────────┐
   │   Vertex AI          │                   │   GKE Cluster            │
   │                      │                   │   ┌──────────────────┐   │
   │  ┌──────────┐        │                   │   │ serving ns       │   │
   │  │ Ingest   │        │     Model         │   │                  │   │
   │  │          ├────┐   │     artifact      │   │  wine-classifier │   │
   │  └──────────┘    │   │    ┌──────────┐   │   │  (HPA 2→10)      │   │
   │  ┌──────────┐    ▼   │    │          │   │   │  ↑ init container│   │
   │  │ Train    ├───→GCS ├───→│ Models   ├──→│   │    downloads     │   │
   │  │ +Baseline│        │    │ Bucket   │   │   │    model+baseline│   │
   │  └──────────┘        │    │ (vers.)  │   │   └────────┬─────────┘   │
   │  ┌──────────┐        │    └──────────┘   │            │             │
   │  │ Evaluate │        │                   │   ┌────────▼─────────┐   │
   │  │ (≥0.85?) │        │                   │   │ monitoring ns    │   │
   │  └──────────┘        │                   │   │                  │   │
   └──────────────────────┘                   │   │ Prometheus ──────┘   │
                                              │   │     │                │
                                              │   │     ▼                │
                                              │   │  Grafana             │
                                              │   │     ▲                │
                                              │   │     │                │
                                              │   │  Pushgateway         │
                                              │   │     ▲                │
                                              │   │     │                │
                                              │   │  Drift CronJob       │
                                              │   │  (every 15min)       │
                                              │   └──────────────────────┘
                                              └──────────────────────────┘
```

**Flow of a prediction request**: client → GKE service → HPA-managed pod → FastAPI `/predict` → model returns class + probabilities → latency, prediction counter, and feature values recorded as Prometheus metrics → Prometheus scrapes `/metrics` every 15s → Grafana visualizes.

**Flow of drift detection**: CronJob fires every 15 min → init container pulls current baseline from GCS → main container queries Prometheus for live feature averages over last 5 min → computes `|live_mean - baseline_mean| / baseline_std` per feature → pushes `feature_drift_zscore{feature_name}` to Pushgateway → Prometheus scrapes it → alerting rules fire on z-score > 2.

---

## Project structure

```
mlops-gcp/
├── terraform/                    # Infrastructure-as-Code
│   ├── main.tf                   # Provider, backend, API enablement
│   ├── variables.tf              # All configurable values
│   ├── gke.tf                    # Cluster + node pool
│   ├── network.tf                # VPC, subnet, firewall
│   ├── storage.tf                # Data, models, artifacts buckets
│   ├── artifact-registry.tf      # Docker image registry
│   ├── iam.tf                    # Service account setup
│   ├── kubernetes.tf             # Namespaces, K8s SAs
│   └── outputs.tf                # Values for scripts and CI/CD
│
├── pipelines/                    # Vertex AI training pipeline
│   ├── ingest.py                 # Read GCS → validate → train/test split
│   ├── train.py                  # Fit RandomForest, save feature baseline
│   ├── evaluate.py               # Test metrics, register if ≥ threshold
│   ├── pipeline.py               # Wires components together
│   └── run.py                    # Compile + submit to Vertex AI
│
├── serving/                      # Model serving on GKE
│   ├── app.py                    # FastAPI: /predict, /health, /metrics
│   ├── requirements.txt          # Pinned versions
│   ├── Dockerfile                # Slim, non-root, healthcheck
│   ├── download_model.py         # Local dev: fetch latest from GCS
│   ├── deploy.sh                 # Substitutes TF outputs → kubectl apply
│   └── k8s/
│       ├── deployment.yaml       # Init container + serving container
│       ├── service.yaml          # ClusterIP
│       └── hpa.yaml              # 2→10 pods, CPU target 70%
│
├── monitoring/                   # Observability stack
│   ├── values.yaml               # kube-prometheus-stack config
│   ├── podmonitor.yaml           # Scrape config for serving pods
│   ├── deploy.sh                 # Installs Prometheus, Grafana, Pushgateway
│   ├── dashboards/
│   │   └── wine-classifier.json  # 4-panel Grafana dashboard
│   ├── apply-dashboard.sh        # ConfigMap wrapper for auto-provisioning
│   ├── drift_detector.py         # Baseline vs live comparison
│   ├── drift-cronjob.yaml        # Runs every 15 min
│   └── deploy-drift.sh           # Applies the CronJob
│
├── scripts/
│   ├── generate_dataset.py       # Wine dataset CSV generator
│   └── load_test.py              # Concurrent prediction requests
│
├── .github/workflows/
│   ├── retrain.yml               # Triggers Vertex AI pipeline on push
│   ├── deploy.yml                # Builds & deploys container on push
│   └── README.md                 # CI/CD setup guide (WIF + SA key modes)
│
├── Makefile                      # All operations in one place
├── .gitignore
└── README.md
```

---

## Quick start

### Prerequisites

- Google Cloud SDK (`gcloud`) authenticated
- Terraform ≥ 1.5
- Python 3.10+
- `kubectl`, `helm`, `docker`

### 1. Infrastructure

```bash
# One-time: create Terraform state bucket
gcloud storage buckets create gs://YOUR_PROJECT-tf-state --location=EU
gcloud storage buckets update gs://YOUR_PROJECT-tf-state --versioning

# Configure and apply
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars → set project_id
make tf-init
make tf-apply            # ~10 min for GKE cluster
make cluster-auth
```

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r serving/requirements.txt
pip install kfp==2.7.0 google-cloud-aiplatform==1.42.1 google-cloud-storage==2.14.0
```

### 3. Upload dataset

```bash
make upload-data
```

### 4. Train a model

```bash
python -m pipelines.run \
    --data-bucket YOUR_PROJECT-mlops-data \
    --model-bucket YOUR_PROJECT-mlops-models \
    --pipeline-bucket YOUR_PROJECT-mlops-pipeline-artifacts \
    --no-cache
```

Monitor the run at: **Console → Vertex AI → Pipelines** (~5-10 min).

Verify model registration:
```bash
gcloud storage cat gs://YOUR_PROJECT-mlops-models/wine-classifier/latest.json
```

### 5. Build and deploy the serving container

```bash
make push-serving
./serving/deploy.sh
```

Verify:
```bash
kubectl get pods -n serving
kubectl port-forward svc/wine-classifier 8080:80 -n serving

# In another terminal
curl http://localhost:8080/health
curl -X POST http://localhost:8080/predict \
    -H "Content-Type: application/json" \
    -d '{"data": [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0]}'
```

### 6. Deploy monitoring stack

```bash
./monitoring/deploy.sh            # Prometheus + Grafana + Pushgateway
./monitoring/apply-dashboard.sh   # Wine Classifier dashboard
./monitoring/deploy-drift.sh      # Drift detection CronJob
```

Access Grafana (`admin / admin`):
```bash
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring
```

### 7. Generate traffic and watch it work

```bash
# Terminal 1
kubectl port-forward svc/wine-classifier 8080:80 -n serving

# Terminal 2
python scripts/load_test.py --url http://localhost:8080 --duration 300 --rps 30

# Terminal 3 — watch HPA scale up
kubectl get hpa -n serving -w
```

### 8. (Optional) Wire up CI/CD

See `.github/workflows/README.md` for GitHub Actions setup. Two auth modes:
- **Workload Identity Federation** (preferred, keyless)
- **Service Account Key** (fallback for IAM-restricted projects)

---

## Architecture decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Orchestration | Vertex AI Pipelines (KFP v2) | Native GCP, managed, typed artifacts |
| Model | scikit-learn RandomForest | Trivial on purpose — infrastructure is the point |
| Dataset | Wine (178 samples, 13 features) | Rich enough for drift detection, fast to train |
| Model storage | Versioned GCS + `latest.json` pointer | Simple, no extra services, easy to inspect |
| Quality gate | Accuracy threshold in evaluate step | Bad models rejected at pipeline time |
| Feature baseline | Saved alongside model during training | Enables drift detection with zero coupling |
| Serving framework | FastAPI | Async, Pydantic schemas, easy Prometheus integration |
| Model loading | Init container from GCS | Decouples model version from container version |
| GKE mode | Standard (not Autopilot) | Control over node pools, monitoring stack |
| Node type | e2-standard-2, spot | 60-91% cheaper than on-demand for dev workloads |
| Autoscaling | HPA on CPU (2→10 pods, target 70%) | Simple, proven, easy to demo |
| Monitoring | kube-prometheus-stack + custom dashboards | Standard Prometheus Operator pattern |
| Drift detection | CronJob → Pushgateway → Prometheus | Lightweight, no extra infra |
| Region | europe-central2 (Warsaw) | Closest to target employer (ING NL/PL) |
| CI/CD | GitHub Actions with dual auth modes | WIF preferred, SA key as fallback |
| Terraform state | GCS backend with versioning | Remote state, drift protection |

---

## Metrics exposed

The serving container exposes custom Prometheus metrics:

| Metric | Type | Purpose |
|--------|------|---------|
| `predictions_total{class_label}` | Counter | Prediction volume per class — detects class imbalance |
| `prediction_latency_seconds` | Histogram | Latency distribution — compute p50/p95/p99 |
| `input_feature_value{feature_name}` | Histogram | Feature distributions — input for drift detection |
| `model_loaded` | Gauge | Model load status (0/1) |

The drift detector pushes:

| Metric | Type | Purpose |
|--------|------|---------|
| `feature_drift_zscore{feature_name}` | Gauge | Normalized deviation from training baseline |

Alerting threshold: `feature_drift_zscore > 2` indicates significant drift.

---

## IAM note

This project runs workloads on the default Compute Engine service account because the GCP project it was built in has org policy restrictions on IAM management. In production, this should be replaced with dedicated least-privilege service accounts bound via Workload Identity — see `terraform/iam.tf` for the documented upgrade path.

The CI/CD workflows already support both authentication modes — switching to Workload Identity Federation is a matter of adding the right secrets and setting `AUTH_MODE=wif`, no code changes required.

---

## Cost

Estimated **~$5-10/day** when running:
- GKE Standard cluster with 2× e2-standard-2 spot nodes
- Vertex AI pipeline execution (~$0.10-0.50 per run)
- GCS storage (cents per month for this scale)
- Artifact Registry (cents per month)

**Zero cost when torn down** (see teardown below).

---

## Teardown

When you're done, tear everything down to avoid charges.

### Quick teardown (keeps Terraform state bucket)

```bash
make tf-destroy
```

This destroys:
- GKE cluster and all workloads running on it
- VPC and networking
- All three GCS buckets (`mlops-data`, `mlops-models`, `mlops-pipeline-artifacts`)
- Artifact Registry repository and all images
- Service accounts created by Terraform

### Full teardown (including state bucket)

If you want to remove absolutely everything:

```bash
# 1. Destroy infrastructure
make tf-destroy

# 2. Delete the Terraform state bucket (created manually, outside TF)
gcloud storage rm --recursive gs://YOUR_PROJECT-tf-state

# 3. Delete the SA key from GitHub Secrets (if using SA key auth)
#    Settings → Secrets and variables → Actions → Delete GCP_SA_KEY

# 4. Revoke the SA key (if you still have the key ID)
gcloud iam service-accounts keys list \
    --iam-account=PROJECT_NUMBER-compute@developer.gserviceaccount.com
gcloud iam service-accounts keys delete KEY_ID \
    --iam-account=PROJECT_NUMBER-compute@developer.gserviceaccount.com
```

### Verify nothing is left

```bash
# Should return empty
gcloud container clusters list
gcloud storage ls
gcloud artifacts repositories list --location=europe-central2
```

---

## Resuming after teardown

Everything is reproducible from zero — that's the point of Infrastructure-as-Code. Full resume sequence:

```bash
make tf-apply            # Recreate infrastructure (~10 min)
make cluster-auth
make upload-data
python -m pipelines.run --data-bucket ... --model-bucket ... --pipeline-bucket ... --no-cache
make push-serving
./serving/deploy.sh
./monitoring/deploy.sh
./monitoring/apply-dashboard.sh
./monitoring/deploy-drift.sh
```

Total time from `tf-apply` to fully operational: ~20 minutes.