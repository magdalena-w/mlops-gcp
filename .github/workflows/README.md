# GitHub Actions CI/CD Setup

Two workflows power continuous delivery:

- **`retrain.yml`** — triggers the Vertex AI training pipeline on pushes to `pipelines/` or manually
- **`deploy.yml`** — builds and deploys the serving container on pushes to `serving/`

Both workflows need to authenticate to GCP. Pick ONE of the two modes below.

## Repository variables (both modes)

Go to **Settings → Secrets and variables → Actions → Variables tab** and create:

| Name | Value |
|------|-------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `AUTH_MODE` | `wif` or `key` (default: `key` if unset) |

---

## Mode 1: Workload Identity Federation (preferred)

Keyless authentication via OIDC. No long-lived secrets. **Requires IAM permissions** — use this if your project allows WIF.

### One-time setup

```bash
PROJECT_ID="your-project-id"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
REPO="YOUR_GITHUB_USERNAME/mlops-gcp"
SA_EMAIL="vertex-pipeline-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# 1. Create workload identity pool
gcloud iam workload-identity-pools create github-pool \
    --location=global \
    --display-name="GitHub Actions Pool"

# 2. Create OIDC provider restricted to your repo
gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location=global \
    --workload-identity-pool=github-pool \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '${REPO}'"

# 3. Allow GitHub Actions to impersonate the pipeline SA
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

### Secrets to add

| Name | Value |
|------|-------|
| `WIF_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | `vertex-pipeline-sa@PROJECT_ID.iam.gserviceaccount.com` |

Set variable `AUTH_MODE=wif`.

---

## Mode 2: Service Account Key (fallback)

Use this if your project blocks WIF setup (like in this learning environment). **Less secure** — the key is a long-lived credential. Rotate regularly.

### One-time setup

```bash
PROJECT_ID="your-project-id"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Generate a key for the default compute SA
gcloud iam service-accounts keys create gcp-sa-key.json \
    --iam-account=$SA_EMAIL

# Copy the full contents of gcp-sa-key.json
cat gcp-sa-key.json

# IMPORTANT: delete the local file after copying
rm gcp-sa-key.json
```

### Secrets to add

| Name | Value |
|------|-------|
| `GCP_SA_KEY` | Full JSON contents of the key file |

Set variable `AUTH_MODE=key` (or leave unset — it's the default).

---

## Testing the workflows

### Trigger retraining manually

```bash
gh workflow run retrain.yml \
    -f n_estimators=200 \
    -f max_depth=10 \
    -f accuracy_threshold=0.90
```

Or via the Actions tab → Retrain Model → Run workflow.

### Trigger deploy manually

```bash
gh workflow run deploy.yml
```

### Trigger via code push

```bash
# Changes in serving/ → triggers deploy
echo "# comment" >> serving/app.py
git commit -am "trigger deploy"
git push

# Changes in pipelines/ → triggers retrain
echo "# comment" >> pipelines/train.py
git commit -am "trigger retrain"
git push
```

## What the workflows do

### retrain.yml
1. Checks out code
2. Authenticates to GCP
3. Regenerates and uploads the dataset to GCS
4. Submits the Vertex AI pipeline with `--no-cache`
5. Pipeline runs async — check Vertex AI Console for progress

### deploy.yml
1. Checks out code
2. Authenticates to GCP
3. Builds the serving container for `linux/amd64`
4. Pushes to Artifact Registry with commit SHA tag
5. Updates the GKE deployment to the new image
6. Waits for rollout to complete