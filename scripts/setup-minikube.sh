#!/usr/bin/env bash
# setup-minikube.sh
# Sets up a local Minikube cluster with all required addons.
# Run once before anything else.
# Requirements: minikube, kubectl, helm installed on your Mac.
# Install: brew install minikube kubectl helm

set -euo pipefail

# ── Helper: retry a command up to N times with delay ─────────────────────────
retry() {
  local attempts=$1; shift
  local delay=$2;    shift
  local i=1
  until "$@"; do
    if [ $i -ge $attempts ]; then
      echo "ERROR: command failed after $attempts attempts: $*"
      return 1
    fi
    echo "  attempt $i/$attempts failed – retrying in ${delay}s …"
    sleep "$delay"
    ((i++))
  done
}

# ── Helper: wait until kube-apiserver is reachable ───────────────────────────
wait_for_apiserver() {
  echo "Waiting for kube-apiserver to be ready …"
  until kubectl cluster-info &>/dev/null; do
    echo "  API server not ready yet, waiting 5s …"
    sleep 5
  done
  echo "  API server ready ✓"

  # Extra safety: wait for core system pods
  kubectl wait --for=condition=Ready pods \
    -n kube-system -l tier=control-plane \
    --timeout=120s 2>/dev/null || true
  sleep 5   # brief settle time
}

echo "=== 1. Start Minikube ==="
minikube start \
  --cpus=4 \
  --memory=8192 \
  --disk-size=40g \
  --driver=docker \
  --kubernetes-version=v1.29.0 \
  --wait=all \
  --wait-timeout=5m

# Ensure API server is fully up before enabling addons
wait_for_apiserver

echo "=== 2. Enable addons (with retry) ==="
retry 5 10 minikube addons enable ingress          # nginx ingress controller
retry 5 10 minikube addons enable metrics-server   # needed for HPA
retry 5 10 minikube addons enable storage-provisioner

echo "Waiting for ingress controller to be ready …"
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s || true

echo "=== 3. Add /etc/hosts entry ==="
MINIKUBE_IP=$(minikube ip)
echo "Minikube IP: $MINIKUBE_IP"

if ! grep -q "llm.local" /etc/hosts; then
  echo "$MINIKUBE_IP llm.local" | sudo tee -a /etc/hosts
  echo "Added llm.local → $MINIKUBE_IP to /etc/hosts"
else
  echo "llm.local already in /etc/hosts"
fi

echo ""
echo "=== Minikube ready ==="
kubectl get nodes
