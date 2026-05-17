"""
Modal Training Function – QLoRA fine-tune Llama 3.1 8B on A10G GPU
--------------------------------------------------------------------
Triggered by the backend via Modal Python SDK (outbound call, no tunnel needed).

Usage (local test):
  modal run training/modal_train.py \
    --data-path training/data/conversations.jsonl \
    --repo-id   YOUR_HF_USER/llama-3-finetuned \
    --version   v2

Flow:
  1. Backend calls fine_tune.remote(config)  ← async, runs on Modal A10G
  2. Modal downloads base model from HF
  3. QLoRA fine-tune on uploaded JSONL data
  4. Merge adapter + push full model to HF Hub
  5. Returns {"model_name": ..., "version": ...} to backend
  6. Backend updates K8s ConfigMap → ArgoCD rolling update
"""

import json
import os
import tempfile
from dataclasses import dataclass

import modal

# ── Modal App ──────────────────────────────────────────────────────────────────
app = modal.App("llm-platform-training")

# Persistent volume – caches base model download between runs (saves $$$)
model_cache = modal.Volume.from_name("llm-model-cache", create_if_missing=True)

# Docker image with all training deps
training_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.6.0",
        "transformers==4.48.0",
        "peft==0.10.0",
        "bitsandbytes==0.43.1",
        "accelerate==0.34.0",
        "datasets==2.19.1",
        "huggingface-hub==0.27.0",
        "trl==0.8.6",
        "scipy",
        "einops",
    )
)


# ── Config dataclass ───────────────────────────────────────────────────────────
@dataclass
class TrainConfig:
    base_model: str          # e.g. "meta-llama/Meta-Llama-3.1-8B"
    hf_repo_id: str          # destination e.g. "myuser/llama-3-finetuned-v2"
    version_tag: str         # e.g. "v2"
    training_data: str       # JSONL content as string
    hf_token: str            # HuggingFace write token
    epochs: int = 2
    batch_size: int = 2
    max_length: int = 512
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05


# ── Main training function ─────────────────────────────────────────────────────
@app.function(
    image=training_image,
    gpu=modal.gpu.A10G(),           # 24GB VRAM – fits Llama 3.1 8B in 4-bit
    timeout=7200,                    # 2 hours max
    volumes={"/model-cache": model_cache},
    secrets=[modal.Secret.from_name("hf-secret")],  # HF_TOKEN env var
)
def fine_tune(config_dict: dict) -> dict:
    """
    Run QLoRA fine-tuning on Modal A10G GPU.
    Returns {"model_name": str, "version": str} on success.
    """
    import torch
    from datasets import Dataset
    from peft import (
        LoraConfig,
        TaskType,
        get_peft_model,
        prepare_model_for_kbit_training,
    )
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )
    from huggingface_hub import HfApi

    cfg = TrainConfig(**config_dict)
    hf_token = cfg.hf_token or os.environ.get("HF_TOKEN")

    print(f"[Modal] Base model : {cfg.base_model}")
    print(f"[Modal] Target repo: {cfg.hf_repo_id}")
    print(f"[Modal] GPU        : {torch.cuda.get_device_name(0)}")

    # ── 1. Load tokenizer ───────────────────────────────────────────────────
    tokenizer = AutoTokenizer.from_pretrained(
        cfg.base_model,
        token=hf_token,
        cache_dir="/model-cache",
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # ── 2. Load model in 4-bit (QLoRA) ─────────────────────────────────────
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        token=hf_token,
        cache_dir="/model-cache",
    )
    model = prepare_model_for_kbit_training(model)

    # ── 3. Attach LoRA adapters ─────────────────────────────────────────────
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── 4. Prepare dataset ──────────────────────────────────────────────────
    records = [json.loads(l) for l in cfg.training_data.strip().splitlines() if l.strip()]

    texts = []
    for rec in records:
        text = ""
        for turn in rec.get("conversations", []):
            text += turn["content"] + tokenizer.eos_token
        texts.append(text)

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=cfg.max_length,
            padding="max_length",
        )

    ds = Dataset.from_dict({"text": texts}).map(
        tokenize, batched=True, remove_columns=["text"]
    )
    split = ds.train_test_split(test_size=0.1, seed=42)

    # ── 5. Train ────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as output_dir:
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=cfg.epochs,
            per_device_train_batch_size=cfg.batch_size,
            per_device_eval_batch_size=cfg.batch_size,
            gradient_accumulation_steps=4,
            warmup_steps=50,
            weight_decay=0.01,
            fp16=True,
            logging_steps=10,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            report_to="none",
            push_to_hub=False,
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=split["train"],
            eval_dataset=split["test"],
            data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
        )

        print("[Modal] Starting training …")
        trainer.train()
        trainer.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)
        print("[Modal] Training complete.")

        # ── 6. Push to HuggingFace Hub ──────────────────────────────────────
        print(f"[Modal] Pushing to {cfg.hf_repo_id} …")
        model.push_to_hub(
            cfg.hf_repo_id,
            token=hf_token,
            commit_message=f"Release {cfg.version_tag} (QLoRA fine-tune)",
        )
        tokenizer.push_to_hub(cfg.hf_repo_id, token=hf_token)

        # Tag version
        api = HfApi(token=hf_token)
        api.create_tag(cfg.hf_repo_id, tag=cfg.version_tag, exist_ok=True)

    print(f"[Modal] Done. Model live at https://huggingface.co/{cfg.hf_repo_id}")
    return {"model_name": cfg.hf_repo_id, "version": cfg.version_tag}


# ── CLI entrypoint for local testing ──────────────────────────────────────────
@app.local_entrypoint()
def main(
    data_path: str = "training/data/conversations.jsonl",
    repo_id: str = "",
    version: str = "v2",
    base_model: str = "meta-llama/Meta-Llama-3.1-8B",
    epochs: int = 2,
):
    if not repo_id:
        raise ValueError("--repo-id required (e.g. myuser/llama-v2)")

    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        raise ValueError("Set HF_TOKEN env var")

    with open(data_path) as f:
        training_data = f.read()

    config = {
        "base_model": base_model,
        "hf_repo_id": repo_id,
        "version_tag": version,
        "training_data": training_data,
        "hf_token": hf_token,
        "epochs": epochs,
    }

    result = fine_tune.remote(config)
    print(f"Result: {result}")
