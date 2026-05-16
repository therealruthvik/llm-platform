"""
Upload training data to HuggingFace Hub as a dataset.
------------------------------------------------------
DevOps engineer runs this before triggering training.

Usage:
  python upload_data.py \
    --data_path ./data/conversations.jsonl \
    --dataset_repo YOUR_HF_USERNAME/llm-training-data \
    --hf_token $HF_TOKEN

Expected JSONL format (one JSON object per line):
  {"conversations": [
      {"role": "user",      "content": "What is Python?"},
      {"role": "assistant", "content": "Python is a programming language."}
  ]}
"""

import argparse
import logging
import os

from huggingface_hub import HfApi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def upload(args):
    api = HfApi(token=args.hf_token)

    # Create dataset repo if it doesn't exist
    api.create_repo(
        repo_id=args.dataset_repo,
        repo_type="dataset",
        exist_ok=True,
        private=True,  # keep training data private
    )

    logger.info(f"Uploading {args.data_path} → {args.dataset_repo}")
    api.upload_file(
        path_or_fileobj=args.data_path,
        path_in_repo="conversations.jsonl",
        repo_id=args.dataset_repo,
        repo_type="dataset",
        commit_message="Upload training data",
    )

    logger.info(
        f"Dataset uploaded: https://huggingface.co/datasets/{args.dataset_repo}"
    )
    logger.info("Next step: trigger GitHub Actions 'model-update' workflow manually.")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data_path", required=True, help="Path to local JSONL file")
    p.add_argument(
        "--dataset_repo", required=True, help="e.g. myuser/llm-training-data"
    )
    p.add_argument("--hf_token", default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.hf_token:
        args.hf_token = os.environ.get("HF_TOKEN")
    if not args.hf_token:
        raise ValueError("Provide --hf_token or set HF_TOKEN env var")
    upload(args)
