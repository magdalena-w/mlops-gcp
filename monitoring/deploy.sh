#!/usr/bin/env bash
# ============================================================================
# Deploy monitoring stack (Prometheus + Grafana) to GKE
# ============================================================================
# Installs kube-prometheus-stack via Helm, then applies the PodMonitor
# so Prometheus scrapes our wine-classifier pods.
#
# Usage: ./monitoring/deploy.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Adding Helm repo ==="
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

echo ""
echo "=== Installing kube-prometheus-stack ==="
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --values "$SCRIPT_DIR/values.yaml" \
    --wait \
    --timeout 5m

echo ""
echo "=== Installing Prometheus Pushgateway ==="
helm upgrade --install pushgateway prometheus-community/prometheus-pushgateway \
    --namespace monitoring \
    --set serviceMonitor.enabled=true \
    --set serviceMonitor.additionalLabels.release=monitoring \
    --wait \
    --timeout 2m

echo ""
echo "=== Applying PodMonitor for wine-classifier ==="
kubectl apply -f "$SCRIPT_DIR/podmonitor.yaml"

echo ""
echo "=== Status ==="
kubectl get pods -n monitoring

echo ""
echo "=== Access ==="
echo "Grafana:    kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring"
echo "            Then open http://localhost:3000 (admin / admin)"
echo ""
echo "Prometheus: kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring"
echo "            Then open http://localhost:9090"