---
title: Quickstart — run a local Jev-compatible API on Mac
description: Install OpenJev Multimodal with uv and llama.cpp. Run Qwen on Apple Silicon, try the local playground, and send your first typed decision request.
---

# Start locally

OpenJev Multimodal turns text and images into typed decisions on your Mac. You need an Apple Silicon Mac, Python 3.11 or later, and enough memory for your chosen model. Start with the 4B `balanced` profile on a 16 GB or larger Mac; use `fast` for a smaller footprint. These are practical starting points, not measured minimum-memory guarantees.

## Install and run

```bash
brew install uv llama.cpp
git clone https://github.com/Hand-In/openjev-multimodal.git
cd openjev-multimodal
uv sync --frozen
uv run openjev serve
```

The first run downloads the pinned model and vision projector. Subsequent runs use the local Hugging Face cache. Open **[localhost:8000/playground](http://localhost:8000/playground)** to try text and images. The interactive API reference is at **[localhost:8000/docs](http://localhost:8000/docs)**.

llama.cpp build **b9670** is the verified baseline. Use that build or a newer version with `/props.media_marker` and `post_sampling_probs`. Update Homebrew if these features are missing.

## Your first decision

```bash
curl http://127.0.0.1:8000/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "jev-latest",
    "state": "I was charged twice. Please refund the duplicate.",
    "questions": {
      "refund": {
        "type": "noul",
        "instructions": "Does the customer request a refund?"
      },
      "team": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
          "billing": "Payments and refunds",
          "technical": "Software bugs"
        }
      }
    }
  }'
```

The response contains `answers.refund.noul`, `answers.team.choice`, the full choice distribution and usage. Two questions consume **two output tokens**. Input processing still costs time; images and long contexts take longer.

## Choose a profile

```bash
uv run openjev serve --profile fast      # Qwen3.5-0.8B Q4_K_M
uv run openjev serve --profile balanced  # Qwen3.5-4B Q4_K_M (default)
uv run openjev serve --profile quality   # Qwen3.6-35B-A3B UD-Q4_K_XL
```

Run one profile at a time. The server uses one inference slot and four CPU threads by default. `--threads 2` further limits CPU work. Stop with **Ctrl+C**; the CLI shuts down its own backend.

## Existing weights or backend

```bash
uv run openjev serve --profile quality \
  --model-file /path/to/model.gguf \
  --mmproj-file /path/to/mmproj.gguf

uv run openjev serve --connect http://127.0.0.1:18081
```

Use a matching projector. An existing backend must expose native llama.cpp endpoints, support post-sampling probabilities, disable thinking, use one slot, and load a projector for vision. Configure its context and image-token limits consistently with `--context` and `--image-tokens`.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `--port` | `8000` | API and local playground |
| `--backend-port` | `18081` | Private localhost inference server |
| `--context` | `8192` | Per-question context limit |
| `--image-tokens` | `512` | Backend image-token budget per image |
| `--threads` | `4` | CPU and prompt-processing threads |
| `OPENJEV_API_KEY` | unset | Bearer authentication on `/v1/*` |
| `OPENJEV_REQUEST_TIMEOUT` | `120` | Evaluation deadline including queue time |
| `OPENJEV_MAX_CONCURRENT_REQUESTS` | `4` | Active/queued evaluations; inference stays serial |
| `OPENJEV_IMAGE_MAX_EDGE` | `1024` | Longest image edge after resizing |
| `OPENJEV_IMAGE_ALIGN` | `32` | Visual-token edge in pixels; oversized images are resized once, straight to the encoder's size (`0` turns this off) |
| `OPENJEV_PRIME_SHARED_PREFIX` | `true` | Read the shared state once for multi-question requests |
| `OPENJEV_TEMPLATE_CACHE` | `true` | Reuse a chat-template skeleton verified against the backend |
| `OPENJEV_RESPONSE_TIMING` | `true` | Add the `timing` object to responses; headers always carry it |

Use environment variables or a local `.env`. Keep credentials out of Git. The API binds to `127.0.0.1`. For an intentional network deployment, use authentication and a TLS reverse proxy.

```bash
uv run openjev doctor
curl http://127.0.0.1:8000/health
uv run openjev schema > openapi.json
```

GitHub Pages hosts this documentation. Your Mac hosts the inference API.
