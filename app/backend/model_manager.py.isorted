"""
Model Manager – loads model from HuggingFace Hub and provides inference.
Swapping model = restart pod (K8s rolling update handles this).
"""

import logging
import time
from typing import Dict, List

from config import HF_TOKEN, MAX_HISTORY_TURNS, MAX_NEW_TOKENS, MODEL_NAME
from metrics import TOKENS_GENERATED

logger = logging.getLogger(__name__)


class ModelManager:
    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.device = "cpu"  # updated in load() once torch is imported

    def load(self) -> None:
        """Download and load model + tokenizer from HuggingFace Hub."""
        # Lazy imports – keeps torch/transformers out of module scope so
        # unit tests can run without installing the heavy ML packages.
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        logger.info(f"Loading model: {MODEL_NAME}")
        start = time.time()

        kwargs = {"token": HF_TOKEN} if HF_TOKEN else {}

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, **kwargs)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            **kwargs,
        ).to(self.device)
        self.model.eval()

        elapsed = time.time() - start
        logger.info(f"Model loaded in {elapsed:.1f}s")

    def generate(
        self, history: List[Dict[str, str]], user_message: str
    ) -> str:  # noqa: E501
        """
        Generate a response given conversation history.

        history: [{"role": "user"|"assistant", "content": "..."}]
        Returns: assistant reply string
        """
        import torch

        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model not loaded")

        # Keep last N turns to stay within token budget
        recent = history[-(MAX_HISTORY_TURNS * 2) :]

        # Build input – DialoGPT uses EOS token as turn separator
        input_ids = None
        for turn in recent:
            text = turn["content"] + self.tokenizer.eos_token
            ids = self.tokenizer.encode(text, return_tensors="pt")
            input_ids = (
                ids if input_ids is None else torch.cat([input_ids, ids], dim=-1)
            )

        # Append current user message
        user_ids = self.tokenizer.encode(
            user_message + self.tokenizer.eos_token, return_tensors="pt"
        )
        input_ids = (
            user_ids if input_ids is None else torch.cat([input_ids, user_ids], dim=-1)
        )
        input_ids = input_ids.to(self.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                input_ids,
                max_new_tokens=MAX_NEW_TOKENS,
                pad_token_id=self.tokenizer.eos_token_id,
                do_sample=True,
                top_p=0.92,
                temperature=0.75,
            )

        # Decode only the newly generated tokens
        new_tokens = output_ids[:, input_ids.shape[-1] :]
        reply = self.tokenizer.decode(new_tokens[0], skip_special_tokens=True)

        TOKENS_GENERATED.inc(new_tokens.shape[-1])
        return reply.strip()


# Singleton – imported by main.py
manager = ModelManager()
