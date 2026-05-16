"""
FastAPI LLM Chat Backend
------------------------
GET  /health        – liveness + model version info
GET  /version       – current model name + version (used by CI verify script)
POST /chat          – generate reply
GET  /metrics       – Prometheus scrape endpoint
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from pydantic import BaseModel

from config import MODEL_NAME, MODEL_VERSION
from model_manager import manager
from metrics import (
    REQUEST_COUNT,
    INFERENCE_LATENCY,
    set_model_info,
)

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
