"""
FastAPI LLM Chat Backend
------------------------
GET  /health                    – liveness + model version info
GET  /version                   – current model name + version
POST /chat                      – generate reply
GET  /metrics                   – Prometheus scrape endpoint
POST /api/train                 – submit Modal training job
GET  /api/training-status/{id}  – poll job status + logs
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List

from config import MODEL_NAME, MODEL_VERSION
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from metrics import (
    INFERENCE_LATENCY,
    REQUEST_COUNT,
    set_model_info,
)
from model_manager import manager
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from starlette.responses import Response
from training_manager import get_job, start_training

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Lifespan (startup/shutdown) ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up – loading model …")
    manager.load()
    set_model_info(MODEL_NAME, MODEL_VERSION)
    logger.info(f"Ready – model={MODEL_NAME} version={MODEL_VERSION}")
    yield
    logger.info("Shutting down")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="LLM Chat API", version=MODEL_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


class ChatResponse(BaseModel):
    reply: str
    model_name: str
    model_version: str
    latency_ms: float


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "model_loaded": manager.model is not None,
    }


@app.get("/version")
def version():
    """Lightweight endpoint used by CI verify script to confirm model update."""
    return {"model_name": MODEL_NAME, "model_version": MODEL_VERSION}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if manager.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    history = [m.model_dump() for m in req.history]

    start = time.time()
    try:
        reply = manager.generate(history, req.message)
        REQUEST_COUNT.labels(status="success").inc()
    except Exception as exc:
        REQUEST_COUNT.labels(status="error").inc()
        logger.exception("Inference error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency = (time.time() - start) * 1000
    INFERENCE_LATENCY.observe(latency / 1000)

    return ChatResponse(
        reply=reply,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        latency_ms=round(latency, 2),
    )


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Training API ──────────────────────────────────────────────────────────────


class TrainRequest(BaseModel):
    base_model: str = "meta-llama/Meta-Llama-3.1-8B"
    hf_repo_id: str               # e.g. "myuser/llama-v2"
    version_tag: str = "v2"
    training_data: str            # JSONL content as string
    epochs: int = 2
    lora_r: int = 16
    lora_alpha: int = 32


@app.post("/api/train")
def start_train_job(req: TrainRequest):
    """
    Submit a Modal training job.
    Returns job_id – poll /api/training-status/{job_id} for progress.
    """
    hf_token = os.getenv("HF_TOKEN", "")
    if not hf_token:
        raise HTTPException(status_code=500, detail="HF_TOKEN not set on server")

    config = {
        "base_model": req.base_model,
        "hf_repo_id": req.hf_repo_id,
        "version_tag": req.version_tag,
        "training_data": req.training_data,
        "hf_token": hf_token,
        "epochs": req.epochs,
        "lora_r": req.lora_r,
        "lora_alpha": req.lora_alpha,
    }

    job_id = start_training(config)
    logger.info(f"Training job {job_id} started for {req.hf_repo_id}")
    return {"job_id": job_id, "status": "pending"}


@app.post("/api/train/upload")
async def start_train_job_upload(
    file: UploadFile = File(...),
    base_model: str = Form("meta-llama/Meta-Llama-3.1-8B"),
    hf_repo_id: str = Form(...),
    version_tag: str = Form("v2"),
    epochs: int = Form(2),
    lora_r: int = Form(16),
    lora_alpha: int = Form(32),
):
    """
    Same as /api/train but accepts multipart file upload for training data.
    Use this from the WebUI file picker.
    """
    hf_token = os.getenv("HF_TOKEN", "")
    if not hf_token:
        raise HTTPException(status_code=500, detail="HF_TOKEN not set on server")

    content = await file.read()
    training_data = content.decode("utf-8")

    # Basic validation
    lines = [ln for ln in training_data.splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    import json
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
            if "conversations" not in obj:
                raise ValueError("missing 'conversations' key")
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid JSONL at line {i+1}: {e}"
            )

    config = {
        "base_model": base_model,
        "hf_repo_id": hf_repo_id,
        "version_tag": version_tag,
        "training_data": training_data,
        "hf_token": hf_token,
        "epochs": epochs,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
    }

    job_id = start_training(config)
    logger.info(f"Training job {job_id} started (upload) for {hf_repo_id}")
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/training-status/{job_id}")
def training_status(job_id: str):
    """Poll this endpoint to get job progress and logs."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
