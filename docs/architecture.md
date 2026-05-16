# LLM Platform – Architecture & Runbook

## Overview

A production-grade LLM chat platform that runs on a local Minikube cluster (zero cloud cost).
The platform supports model versioning, a full CI/CD pipeline, and Prometheus/Grafana observability.

---

## Stack

| Layer | Tool | Cost |
|---|---|---|
| Cluster | Minikube (local) | Free |
| Container Registry | GitHub Container Registry (GHCR) | Free |
| CI/CD – Build | GitHub Actions | Free (2000 min/mo) |
| CI/CD – Deploy | ArgoCD (self-hosted in cluster) | Free |
| Model Registry | HuggingFace Hub | Free |
| Observability | Prometheus + Grafana (in cluster) | Free |
| Frontend | React + Vite + nginx | Free |
| Backend | FastAPI + Transformers | Free |

---

## Project Structure

```
llmpipeline/
├── app/
│   ├── backend/          FastAPI inference server
│   └── frontend/         React chat UI
├── training/             Fine-tuning scripts
├── k8s/                  Kubernetes manifests (watched by ArgoCD)
│   ├── backend/          Deployment, Service, ConfigMap, HPA
│   ├── frontend/         Deployment, Service
│   ├── ingress/          Nginx Ingress
│   ├── monitoring/       ServiceMonitor
│   └── argocd/           ArgoCD Application
├── monitoring/           Local dev Prometheus + Grafana config
├── .github/workflows/    CI and model-update pipelines
├── scripts/              Setup + verification scripts
└── docs/                 This file
```

---

## First-Time Setup

### Prerequisites
```bash
brew install minikube kubectl helm git node python@3.11
```

### 1. Start cluster
```bash
./scripts/setup-minikube.sh
```

### 2. Install ArgoCD
```bash
./scripts/setup-argocd.sh https://github.com/YOUR_USER/llm-platform.git
# UI: http://localhost:8888  user: admin
```

### 3. Install Prometheus + Grafana
```bash
./scripts/setup-monitoring.sh
# Grafana: http://localhost:3001  user: admin / pass: admin
# Prometheus: http://localhost:9090
```

### 4. Set HuggingFace secret
```bash
kubectl create secret generic hf-secret \
  --from-literal=HF_TOKEN=hf_YOUR_TOKEN \
  -n llm-platform
```

### 5. Push initial images (first run only)
GitHub Actions CI will push images to GHCR on the first push to `main`.
Or build locally:
```bash
docker build -t ghcr.io/YOUR_USER/llm-backend:latest app/backend
docker build -t ghcr.io/YOUR_USER/llm-frontend:latest app/frontend
docker push ghcr.io/YOUR_USER/llm-backend:latest
docker push ghcr.io/YOUR_USER/llm-frontend:latest
```

### 6. Apply namespace + app registration
ArgoCD handles everything once you push to main. For initial bootstrap:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/argocd/application.yaml
```

---

## Model Versioning

### How model config flows

```
k8s/backend/configmap.yaml
  MODEL_NAME: "microsoft/DialoGPT-medium"
  MODEL_VERSION: "v1"
        ↓
  K8s ConfigMap (envFrom)
        ↓
  Backend pod env vars
        ↓
  GET /version  →  {"model_name": "...", "model_version": "v1"}
  GET /metrics  →  llm_model_version 1
```

### To change model manually
1. Edit `k8s/backend/configmap.yaml`
2. Commit + push to `main`
3. ArgoCD detects change → rolling restart of backend pods
4. New pods load new model from HuggingFace

---

## Model Update Pipeline (v1 → v2)

### Full DevOps flow

```
1. Prepare data
   └─ Add conversations to training/data/conversations.jsonl
   └─ python training/upload_data.py \
        --data_path ./training/data/conversations.jsonl \
        --dataset_repo YOUR_USER/llm-training-data \
        --hf_token $HF_TOKEN

2. Trigger pipeline (GitHub Actions UI)
   └─ Go to: Actions → "Model Update Pipeline (Manual)" → Run workflow
   └─ Fill inputs:
        base_model:      microsoft/DialoGPT-medium
        dataset_repo:    YOUR_USER/llm-training-data
        new_model_repo:  YOUR_USER/dialogpt-v2
        new_version_tag: v2
        epochs:          3

3. Pipeline runs:
   validate-inputs → download-data → train → evaluate → push-to-hub
   → update-k8s-config → verify-model-update

4. ArgoCD detects configmap.yaml change → rolling update
5. New pods pull model from HuggingFace and serve v2
```

### Verify manually
```bash
./scripts/verify-model-update.sh v2 YOUR_USER/dialogpt-v2
```

---

## CI Pipeline Checks

Every PR/push to `main` runs:

| Step | Tool | What it checks |
|---|---|---|
| Lint | flake8, black, isort, ESLint | Code style |
| Unit Tests | pytest | API correctness (model mocked) |
| Python SAST | Bandit | Dangerous code patterns |
| Dependency CVEs | pip-audit | Known vulnerabilities |
| Filesystem scan | Trivy | Secrets, CVEs in source |
| Docker build | docker buildx | Image builds cleanly |
| Image CVE scan | Trivy | Critical vulns in image |
| Tag update | sed + git | manifest updated with new SHA |

All steps must pass before image is tagged `latest`.

---

## Observability

### Metrics exposed by backend (`/metrics`)

| Metric | Type | Description |
|---|---|---|
| `llm_request_total{status}` | Counter | Total requests (success/error) |
| `llm_inference_duration_seconds` | Histogram | Per-request latency |
| `llm_tokens_generated_total` | Counter | Total tokens generated |
| `llm_model_version` | Gauge | Current model version (numeric) |
| `llm_model_info` | Info | Model name + version string |

### Grafana Dashboard
- Import `monitoring/grafana/provisioning/dashboards/llm_dashboard.json`
- Panels: Model Version, Requests/min, p50/p95/p99 latency, Error rate, Tokens/min

### Key alerts to add (manual in Grafana)
- Error rate > 5% for 5m
- p99 latency > 10s
- `llm_model_version` changes (model rollout event)

---

## Local Dev (no cluster)

```bash
# Copy and set HF_TOKEN
cp .env.example .env   # add HF_TOKEN=hf_xxx

# Start everything
docker compose up --build

# Services:
# Frontend  → http://localhost:3000
# Backend   → http://localhost:8000
# Grafana   → http://localhost:3001
# Prometheus→ http://localhost:9090
```

---

## GitHub Secrets Required

| Secret | Value |
|---|---|
| `HF_TOKEN` | HuggingFace write token |
| `KUBECONFIG` | base64-encoded kubeconfig (for verify step) |

```bash
# Encode kubeconfig:
cat ~/.kube/config | base64 | pbcopy
# Paste into GitHub Settings → Secrets → KUBECONFIG
```
