"""
Push a locally trained model to HuggingFace Hub.
-------------------------------------------------
Usage:
  python push_to_hub.py \
    --model_dir ./output \
    --repo_id YOUR_HF_USERNAME/my-dialogpt-v2 \
    --version_tag v2 \
    --hf_token $HF_TOKEN

The script:
1. Pushes model + tokenizer to Hub
2. Creates/updates a model card with version metadata
3. Prints the Hub URL – copy this into k8s/backend/configmap.yaml
"""

import argparse
import logging
from pathlib import Path

from huggingface_hub import HfApi, ModelCard, ModelCardData
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_CARD_TEMPLATE = """
---
language: en
license: mit
tags:
  - conversational
  - llm-pipeline
  - version: {version}
---

# {repo_id}

Fine-tuned conversational model – **{version}**.

## Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("{repo_id}")
model     = AutoModelForCausalLM.from_pretrained("{repo_id}")
```

## Version history

| Version | Notes |
|---------|-------|
| {version} | Latest |
"""


def push(args):
    logger.info(f"Pushing {args.model_dir} → {args.repo_id} as {args.version_tag}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForCausalLM.from_pretrained(args.model_dir)

    # Push model + tokenizer
    model.push_to_hub(args.repo_id, token=args.hf_token, commit_message=f"Release {args.version_tag}")
    tokenizer.push_to_hub(args.repo_id, token=args.hf_token)

    # Create/update model card
    card_content = MODEL_CARD_TEMPLATE.format(
        repo_id=args.repo_id,
        version=args.version_tag,
    )
    card = ModelCard(card_content)
    card.push_to_hub(args.repo_id, token=args.hf_token)

    # Tag the commit with version
    api = HfApi(token=args.hf_token)
    api.create_tag(args.repo_id, tag=args.version_tag, exist_ok=True)

    hub_url = f"https://huggingface.co/{args.repo_id}"
    logger.info(f"Model pushed successfully: {hub_url}")
    logger.info(f"Update k8s/backend/configmap.yaml:")
    logger.info(f"  MODEL_NAME: \"{args.repo_id}\"")
    logger.info(f"  MODEL_VERSION: \"{args.version_tag}\"")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model_dir", required=True)
    p.add_argument("--repo_id", required=True, help="e.g. myuser/dialogpt-v2")
    p.add_argument("--version_tag", default="v2")
    p.add_argument("--hf_token", default=None, help="HF write token (or set HF_TOKEN env var)")
    return p.parse_args()


if __name__ == "__main__":
    import os
    args = parse_args()
    if not args.hf_token:
        args.hf_token = os.environ.get("HF_TOKEN")
    if not args.hf_token:
        raise ValueError("Provide --hf_token or set HF_TOKEN env var")
    push(args)
