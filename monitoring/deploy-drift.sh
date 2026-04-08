#!/usr/bin/env bash
# ============================================================================
# Deploy the drift detector CronJob
# ============================================================================
# 1. Creates a ConfigMap containing drift_detector.py
# 2. Substitutes the models bucket name into the CronJob manifest
# 3. Applies the CronJob
#
# Prerequisites: monitoring stack already deployed (./monitoring/deploy.sh)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Reading Terraform outputs ==="
MODELS_BUCKET=$(cd "$REPO_ROOT/terraform" && terraform output -raw models_bucket)
echo "  Models bucket: $MODELS_BUCKET"

echo ""
echo "=== Creating script ConfigMap ==="
kubectl create configmap drift-detector-script \
    --from-file=drift_detector.py="$SCRIPT_DIR/drift_detector.py" \
    --namespace=monitoring \
    --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "=== Applying CronJob ==="
sed "s|MODELS_BUCKET_PLACEHOLDER|$MODELS_BUCKET|g" \
    "$SCRIPT_DIR/drift-cronjob.yaml" | kubectl apply -f -

echo ""
echo "=== Status ==="
kubectl get cronjob feature-drift-detector -n monitoring

echo ""
echo "To trigger a run manually:"
echo "  kubectl create job --from=cronjob/feature-drift-detector drift-test-$(date +%s) -n monitoring"
echo ""
echo "To view logs:"
echo "  kubectl logs -n monitoring -l job-name=drift-test-... -c drift-detector"