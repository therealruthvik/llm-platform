"""
Configuration loaded from environment variables.
MODEL_NAME   : HuggingFace model repo (e.g. microsoft/DialoGPT-medium)
MODEL_VERSION: Semantic label shown in /health and Prometheus metric (e.g. v1, v2)
HF_TOKEN     : Optional – needed for private repos or pushing models
"""

import os

MODEL_NAME: str = os.getenv("MODEL_NAME", "microsoft/DialoGPT-medium")
MODEL_VERSION: str = os.getenv("MODEL_VERSION", "v1")
HF_TOKEN: str | None = os.getenv("HF_TOKEN", None)

MAX_NEW_TOKENS: int = int(os.getenv("MAX_NEW_TOKENS", "200"))
MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "5"))
PORT: int = int(os.getenv("PORT", "8000"))
