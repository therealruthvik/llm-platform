#!/usr/bin/env bash
# setup-argocd.sh
# Installs ArgoCD into the cluster and registers the llm-platform application.
# Run AFTER setup-minikube.sh.

set -euo pipefail

ARGOCD_VERSION="v2.11.0"
REPO_URL="${1:-https://github.com/threalruthvik/llm-platform.git}"

echo "=== 1. Install ArgoCD ==="
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml

echo "=== 2. Wait for ArgoCD to be ready ==="
kubectl wait --for=condition=available deployment/argocd-server \
  -n argocd --timeout=300s

echo "=== 3. Patch ArgoCD server to insecure (no TLS for local) ==="
kubectl patch deployment argocd-server -n argocd \
  --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--insecure"}]'

echo "=== 4. Get initial admin password ==="
ARGOCD_PASS=$(kubectl get secret argocd-initial-admin-secret \
  -n argocd -o jsonpath="{.data.password}" | base64 -d)
echo "ArgoCD admin password: $ARGOCD_PASS"

echo "=== 5. Register llm-platform application ==="
# Update repo URL in application.yaml
sed "s|https://github.com/YOUR_GITHUB_USER/llm-platform.git|${REPO_URL}|g" \
  k8s/argocd/application.yaml | kubectl apply -f -

echo "=== 6. Port-forward ArgoCD UI (background) ==="
kubectl port-forward svc/argocd-server -n argocd 8888:80 &
echo "ArgoCD UI: http://localhost:8888  (user: admin  pass: $ARGOCD_PASS)"

echo ""
echo "=== ArgoCD ready ==="
