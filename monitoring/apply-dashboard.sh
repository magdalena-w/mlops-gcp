#!/usr/bin/env bash
# ============================================================================
# Apply Grafana dashboard as a ConfigMap
# ============================================================================
# kube-prometheus-stack runs a Grafana sidecar that auto-discovers
# ConfigMaps labeled `grafana_dashboard=1` in the monitoring namespace
# and loads them as dashboards. No manual import needed.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_FILE="$SCRIPT_DIR/dashboards/wine-classifier.json"

echo "=== Creating dashboard ConfigMap ==="

kubectl create configmap wine-classifier-dashboard \
    --from-file=wine-classifier.json="$DASHBOARD_FILE" \
    --namespace=monitoring \
    --dry-run=client -o yaml | \
    kubectl label --local -f - grafana_dashboard=1 --dry-run=client -o yaml | \
    kubectl apply -f -

echo ""
echo "Dashboard applied. Grafana sidecar will pick it up within 30 seconds."
echo ""
echo "Access:"
echo "  kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring"
echo "  Then open http://localhost:3000 (admin / admin)"
echo "  Dashboard: Dashboards → Browse → 'Wine Classifier — Model Serving'"