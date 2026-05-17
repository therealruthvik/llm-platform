#!/usr/bin/env bash
# ── Teardown: removes everything created by this project ──────────────────────
set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()    { echo -e "${GREEN}[teardown]${NC} $*"; }
warn()    { echo -e "${YELLOW}[teardown]${NC} $*"; }
confirm() {
  read -r -p "$(echo -e "${RED}$* [y/N]: ${NC}")" ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

echo ""
echo -e "${RED}╔══════════════════════════════════════════════╗${NC}"
echo -e "${RED}║   LLM Platform Teardown — DESTRUCTIVE        ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════╝${NC}"
echo ""
warn "This will delete:"
warn "  • llm-platform namespace + all pods/services/ingress"
warn "  • ArgoCD namespace + application"
warn "  • monitoring namespace (Prometheus/Grafana)"
warn "  • Minikube cluster (optional)"
warn "  • /etc/hosts entry for llm.local"
warn "  • Modal app deployment (optional)"
echo ""
confirm "Continue with teardown?" || { info "Aborted."; exit 0; }

# ── 1. Delete ArgoCD application first (stops GitOps sync) ───────────────────
info "Removing ArgoCD application..."
if command -v argocd &>/dev/null && argocd app list 2>/dev/null | grep -q llm-platform; then
  argocd app delete llm-platform --cascade --yes 2>/dev/null || true
  info "ArgoCD app deleted."
else
  kubectl delete application llm-platform -n argocd 2>/dev/null || true
fi

# ── 2. Delete llm-platform namespace ─────────────────────────────────────────
info "Deleting llm-platform namespace..."
kubectl delete namespace llm-platform --timeout=60s 2>/dev/null || true

# ── 3. Delete monitoring namespace ───────────────────────────────────────────
if kubectl get namespace monitoring &>/dev/null; then
  info "Deleting monitoring namespace..."
  kubectl delete namespace monitoring --timeout=60s 2>/dev/null || true
fi

# ── 4. Delete ArgoCD namespace ────────────────────────────────────────────────
if confirm "Delete ArgoCD namespace? (keeps it if you use ArgoCD for other projects)"; then
  info "Deleting ArgoCD namespace..."
  kubectl delete namespace argocd --timeout=60s 2>/dev/null || true
fi

# ── 5. Remove /etc/hosts entry ────────────────────────────────────────────────
info "Removing llm.local from /etc/hosts..."
sudo sed -i '' '/llm\.local/d' /etc/hosts 2>/dev/null || \
  sudo sed -i '/llm\.local/d' /etc/hosts 2>/dev/null || \
  warn "Could not remove /etc/hosts entry – remove manually: sudo sed -i '' '/llm.local/d' /etc/hosts"

# ── 6. Modal teardown (optional) ─────────────────────────────────────────────
if confirm "Delete Modal app 'llm-platform-training'? (stops future GPU billing)"; then
  if command -v modal &>/dev/null; then
    info "Stopping Modal app..."
    modal app stop llm-platform-training 2>/dev/null || true
    info "Deleting Modal volume cache..."
    modal volume delete llm-model-cache --yes 2>/dev/null || true
  else
    warn "modal CLI not found – delete manually at https://modal.com/apps"
  fi
fi

# ── 7. Minikube (optional) ────────────────────────────────────────────────────
if confirm "Delete Minikube cluster? (deletes ALL local K8s data)"; then
  info "Deleting Minikube cluster..."
  minikube delete
  info "Minikube cluster deleted."
else
  info "Minikube kept. Stop it with: minikube stop"
fi

# ── 8. Docker images (optional) ───────────────────────────────────────────────
if confirm "Remove local Docker images for this project?"; then
  docker images | grep -E "llm-backend|llm-frontend" | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || true
  info "Docker images removed."
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Teardown complete.                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
info "GHCR images still exist at https://github.com/therealruthvik?tab=packages"
info "Delete them manually if needed."
info "HuggingFace models still exist at https://huggingface.co"
