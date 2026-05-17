"""
Training Manager
----------------
- Tracks in-flight training jobs (in-memory, resets on pod restart)
- Spawns Modal training function in a background thread
- Updates K8s ConfigMap + restarts deployment when training completes
"""

import logging
import os
import threading
import time
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── In-memory job store ────────────────────────────────────────────────────────
# { job_id: { status, logs, model_name, version, error, started_at, finished_at } }
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def create_job() -> str:
    job_id = str(uuid4())
    with _lock:
        _jobs[job_id] = {
            "status": "pending",
            "logs": [],
            "model_name": None,
            "version": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs.get(job_id, {}))


def _log(job_id: str, msg: str) -> None:
    logger.info(f"[job:{job_id}] {msg}")
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["logs"].append(msg)


def _set_status(job_id: str, status: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status
            _jobs[job_id].update(kwargs)
            if status in ("completed", "failed"):
                _jobs[job_id]["finished_at"] = time.time()


# ── K8s ConfigMap update ───────────────────────────────────────────────────────


def _update_k8s_model(model_name: str, version: str, job_id: str) -> None:
    """
    Patch the backend ConfigMap with the new model and trigger a rolling restart.
    Falls back to a no-op if kubernetes client is not available (local dev).
    """
    try:
        from kubernetes import client, config as k8s_config

        # Load in-cluster config (works inside K8s pod)
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            # Fallback for local dev with kubeconfig
            k8s_config.load_kube_config()

        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()

        namespace = os.getenv("K8S_NAMESPACE", "llm-platform")
        configmap_name = "backend-config"
        deployment_name = "llm-backend"

        # Patch ConfigMap
        patch_body = {
            "data": {
                "MODEL_NAME": model_name,
                "MODEL_VERSION": version,
            }
        }
        v1.patch_namespaced_config_map(configmap_name, namespace, patch_body)
        _log(job_id, f"ConfigMap updated: {model_name} {version}")

        # Rolling restart (patch annotation with timestamp)
        import datetime

        patch_deployment = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow().isoformat()
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(
            deployment_name, namespace, patch_deployment
        )
        _log(job_id, "Deployment rollout restart triggered")

    except ImportError:
        _log(
            job_id,
            "kubernetes client not installed – skipping K8s update (local dev mode)",
        )
    except Exception as exc:
        _log(job_id, f"K8s update failed: {exc}")
        raise


# ── Background training worker ─────────────────────────────────────────────────


def _run_training(job_id: str, config: dict) -> None:
    """Runs in a background thread. Calls Modal, then updates K8s."""
    _set_status(job_id, "running")
    _log(job_id, "Connecting to Modal …")

    try:
        import modal

        # Look up the deployed Modal function
        # Make sure you have run `modal deploy training/modal_train.py` first
        fine_tune = modal.Function.lookup("llm-platform-training", "fine_tune")

        _log(job_id, "Submitting training job to Modal GPU (A10G) …")
        _log(job_id, f"Base model : {config.get('base_model')}")
        _log(job_id, f"Target repo: {config.get('hf_repo_id')}")
        _log(job_id, f"Epochs     : {config.get('epochs')}")

        # Blocking remote call – Modal runs this on GPU
        result = fine_tune.remote(config)

        model_name = result["model_name"]
        version = result["version"]
        _log(job_id, f"Training complete. Model: {model_name} ({version})")

        # Update K8s so the new model is served
        _log(job_id, "Updating K8s ConfigMap and restarting deployment …")
        _update_k8s_model(model_name, version, job_id)

        _set_status(job_id, "completed", model_name=model_name, version=version)
        _log(job_id, "Done. New model will be live after pod restart (~2min).")

    except ImportError:
        msg = "modal package not installed. Run: pip install modal"
        _log(job_id, msg)
        _set_status(job_id, "failed", error=msg)
    except Exception as exc:
        msg = str(exc)
        _log(job_id, f"Training failed: {msg}")
        _set_status(job_id, "failed", error=msg)


def start_training(config: dict) -> str:
    """Start a training job in the background. Returns job_id."""
    job_id = create_job()
    thread = threading.Thread(target=_run_training, args=(job_id, config), daemon=True)
    thread.start()
    return job_id
