# Modal Setup Guide

## 1. Install Modal + authenticate

```bash
pip install modal
modal setup          # opens browser to authenticate
```

## 2. Create Modal secret for HuggingFace token

```bash
modal secret create hf-secret HF_TOKEN=hf_YOUR_TOKEN
```

This makes `HF_TOKEN` available inside Modal training functions automatically.

## 3. Deploy the training function

```bash
cd /Users/ruthvikg/pythonprojects/llmpipeline
modal deploy training/modal_train.py
```

You'll see output like:
```
✓ Created objects.
├── 🔨 Created fine_tune.
└── App deployed: https://modal.com/apps/llm-platform-training
```

## 4. Test a training run (optional)

```bash
export HF_TOKEN=hf_YOUR_TOKEN
modal run training/modal_train.py \
  --data-path training/data/conversations.jsonl \
  --repo-id   YOUR_HF_USER/llama-test-v2 \
  --version   v2 \
  --epochs    1
```

## 5. Use the WebUI

1. Open http://llm.local → click **🧠 Training** tab
2. Upload your `.jsonl` file
3. Fill in HF repo ID, version tag, epochs
4. Click **🚀 Start Training on Modal**
5. Watch logs update every 3 seconds
6. When complete, cluster auto-updates (ArgoCD rolling restart)

## Full flow diagram

```
WebUI Training Tab
      │
      │  POST /api/train/upload  (multipart: file + config)
      ▼
 FastAPI Backend  (app/backend/training_manager.py)
      │
      │  modal.Function.lookup("llm-platform-training", "fine_tune").remote(config)
      │  ← this is an outbound call, no tunneling needed
      ▼
 Modal A10G GPU (24GB VRAM)
      ├── Downloads Llama 3.1 8B (cached in Modal Volume after first run)
      ├── QLoRA fine-tune on your JSONL data
      ├── Pushes merged model → HuggingFace Hub
      └── Returns {"model_name": "...", "version": "v2"}
                    │
                    ▼
 Backend (training_manager.py)
      ├── Patches K8s ConfigMap via kubernetes-client
      └── Triggers rolling restart of llm-backend deployment
                    │
                    ▼
 ArgoCD detects ConfigMap change → syncs
                    │
                    ▼
 New pod pulls model from HuggingFace → serves v2
```

## GPU cost estimate (Modal)

| Model | GPU | Time | Cost |
|---|---|---|---|
| Llama 3.1 8B QLoRA | A10G (24GB) | ~1h | ~$1.10 |
| Llama 3.1 8B QLoRA | A100 (80GB) | ~40min | ~$2.40 |

Modal free tier gives $30/month credits = ~27 training runs free.
