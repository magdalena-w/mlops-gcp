#!/usr/bin/env bash
# ============================================================================
# Deploy serving stack to GKE
# ============================================================================
# Reads Terraform outputs, substitutes placeholders in K8s manifests,
# and applies them. Run from the repo root:
#
#   ./serving/deploy.sh [IMAGE_TAG]
#
# If IMAGE_TAG is not provided, uses "latest".
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TAG="${1:-latest}"

echo "=== Reading Terraform outputs ==="
REGISTRY=$(cd "$REPO_ROOT/terraform" && terraform output -raw docker_registry_url)
MODELS_BUCKET=$(cd "$REPO_ROOT/terraform" && terraform output -raw models_bucket)

echo "  Registry:     $REGISTRY"
echo "  Models bucket: $MODELS_BUCKET"
echo "  Image tag:     $TAG"

echo ""
echo "=== Applying K8s manifests ==="

# Substitute placeholders and apply each manifest
for manifest in deployment.yaml service.yaml hpa.yaml; do
    echo "  Applying: $manifest"
    sed \
        -e "s|REGISTRY_URL_PLACEHOLDER|$REGISTRY|g" \
        -e "s|IMAGE_TAG_PLACEHOLDER|$TAG|g" \
        -e "s|MODELS_BUCKET_PLACEHOLDER|$MODELS_BUCKET|g" \
        "$SCRIPT_DIR/k8s/$manifest" | kubectl apply -f -
done

echo ""
echo "=== Waiting for rollout ==="
kubectl rollout status deployment/wine-classifier -n serving --timeout=120s

echo ""
echo "=== Status ==="
kubectl get pods -n serving -l app=wine-classifier
echo ""
echo "To test locally:"
echo "  kubectl port-forward svc/wine-classifier 8080:80 -n serving"
echo "  curl http://localhost:8080/health"