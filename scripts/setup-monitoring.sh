#!/usr/bin/env bash
# setup-monitoring.sh
# Installs kube-prometheus-stack (Prometheus + Grafana) via Helm.
# Run AFTER setup-minikube.sh.

set -euo pipefail

echo "=== 1. Add Prometheus Helm repo ==="
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

echo "=== 2. Install kube-prometheus-stack ==="
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.adminPassword=admin \
  --set grafana.persistence.enabled=false \
  --wait --timeout 10m

echo "=== 3. Apply LLM ServiceMonitor ==="
kubectl apply -f k8s/monitoring/servicemonitor.yaml

echo "=== 4. Port-forward Grafana (background) ==="
kubectl port-forward svc/prometheus-grafana -n monitoring 3001:80 &
echo "Grafana: http://localhost:3001  (user: admin  pass: admin)"

echo "=== 5. Port-forward Prometheus (background) ==="
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090 &
echo "Prometheus: http://localhost:9090"

echo ""
echo "=== Monitoring ready ==="
echo "Import Grafana dashboard: monitoring/grafana/provisioning/dashboards/llm_dashboard.json"
