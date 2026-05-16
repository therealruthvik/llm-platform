"""
Fine-tune a HuggingFace causal LM on custom conversation data.
-----------------------------------------------------------------
Usage:
  python train.py \
    --base_model microsoft/DialoGPT-medium \
    --data_path ./data/conversations.jsonl \
    --output_dir ./output \
    --epochs 3 \
    --batch_size 4

Output model is saved locally to --output_dir.
Run push_to_hub.py afterwards to register it on HuggingFace Hub.
"""

import argparse
import json
import logging
import os
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_conversations(data_path: str) -> list[dict]:
    """
    Load conversations from a JSONL file.
    Each line must be a JSON object with a "conversations" list:
    {"conversations": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]}
    """
    records = []
    with open(data_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    logger.info(f"Loaded {len(records)} conversations from {data_path}")
    return records


def conversations_to_text(records: list[dict], tokenizer) -> list[str]:
    """Convert conversation turns to a single training string per record."""
    texts = []
    for record in records:
        text = ""
        for turn in record.get("conversations", []):
            text += turn["content"] + tokenizer.eos_token
        texts.append(text)
    return texts


# ── Tokenisation ──────────────────────────────────────────────────────────────

def tokenize(texts: list[str], tokenizer, max_length: int = 512):
    def _tok(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )

    ds = Dataset.from_dict({"text": texts})
    return ds.map(_tok, batched=True, remove_columns=["text"])


# ── Training ──────────────────────────────────────────────────────────────────

def train(args):
    logger.info(f"Base model : {args.base_model}")
    logger.info(f"Data path  : {args.data_path}")
    logger.info(f"Output dir : {args.output_dir}")

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    # Load tokenizer + model
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )

    # Prepare dataset
    records = load_conversations(args.data_path)
    texts = conversations_to_text(records, tokenizer)
    dataset = tokenize(texts, tokenizer, max_length=args.max_length)

    # 90/10 train/eval split
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_ds, eval_ds = split["train"], split["test"]

    logger.info(f"Train samples: {len(train_ds)}, Eval samples: {len(eval_ds)}")

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        warmup_steps=100,
        weight_decay=0.01,
        logging_dir=os.path.join(args.output_dir, "logs"),
        logging_steps=50,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        fp16=torch.cuda.is_available(),
        report_to="none",              # set to "wandb" if you want tracking
        push_to_hub=False,             # we push manually via push_to_hub.py
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=data_collator,
    )

    logger.info("Starting training …")
    trainer.train()

    logger.info(f"Saving model to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    logger.info("Training complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fine-tune DialoGPT on custom data")
    p.add_argument("--base_model", default="microsoft/DialoGPT-medium")
    p.add_argument("--data_path", required=True, help="Path to JSONL training data")
    p.add_argument("--output_dir", default="./output")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=4)
    p.add_argument("--max_length", type=int, default=512)
    return p.parse_args()


if __name__ == "__main__":
    train(parse_args())
