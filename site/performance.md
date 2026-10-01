---
title: Latency
description: Where request time goes in OpenJev Multimodal and what changed. Shared-prefix priming for hybrid Qwen models, a verified template skeleton and one-step image resizing, measured on all four profiles.
---

# Latency

**Up to 60% faster for several questions about one state. The same decisions.**

Each answer is one output token, so latency is prompt processing: the state, its images and every question. We timed each stage and removed the redundant work.

![Median request latency before and after, balanced profile](/performance.svg)

<div class="latency">

**One question**

|  | fast <span class="model">0.8B</span> | balanced <span class="model">4B</span> | quality <span class="model">35B-A3B</span> | max <span class="model">27B</span> |
| --- | ---: | ---: | ---: | ---: |
| Support ticket | 70 ms <span class="delta">−13%</span> | 278 ms <span class="delta">−4%</span> | 332 ms <span class="delta">−6%</span> | 1.62 s <span class="delta">−1%</span> |
| 1.2k-token policy | 205 ms <span class="delta">−7%</span> | 996 ms <span class="delta">−1%</span> | 1.09 s <span class="delta">−2%</span> | 6.06 s <span class="delta">0%</span> |
| 448×672 screenshot | 136 ms <span class="delta">−7%</span> | 735 ms <span class="delta">−1%</span> | 1.04 s <span class="delta">−3%</span> | 2.75 s <span class="delta">−1%</span> |
| 2048×1536 photo | 256 ms <span class="delta">−18%</span> | 911 ms <span class="delta">−6%</span> | 1.42 s <span class="delta">−1%</span> | 3.72 s <span class="delta">−1%</span> |
| Repeated request | 14 ms <span class="delta">−41%</span> | 35 ms <span class="delta">−20%</span> | 34 ms <span class="delta">−20%</span> | 172 ms <span class="delta">−5%</span> |

**Four questions about the same state**

|  | fast <span class="model">0.8B</span> | balanced <span class="model">4B</span> | quality <span class="model">35B-A3B</span> | max <span class="model">27B</span> |
| --- | ---: | ---: | ---: | ---: |
| Support ticket | 165 ms <span class="delta">−35%</span> | 623 ms <span class="delta">−42%</span> | 859 ms <span class="delta">−35%</span> | 3.38 s <span class="delta">−47%</span> |
| 1.2k-token policy | 311 ms <span class="delta">−41%</span> | 1.43 s <span class="delta">−45%</span> | 1.68 s <span class="delta">−39%</span> | 9.53 s <span class="delta">−47%</span> |
| 448×672 screenshot | 235 ms <span class="delta">−53%</span> | 1.00 s <span class="delta">−60%</span> | 2.09 s <span class="delta">−57%</span> | 4.42 s <span class="delta">−58%</span> |

</div>

Median of 7 interleaved trials, measured at the client, with the change from the previous version. [Method](#method)

## Server time on every response

```json
"timing": {
  "processing_ms": 131.4,
  "parse_ms": 0.9,
  "prepare_ms": 2.1,
  "queue_ms": 0.0,
  "inference_ms": 128.2
}
```

`processing_ms` runs from the moment the request arrives to the moment the response is ready; the stages add up to it. The `x-openjev-processing-ms` and `Server-Timing` headers carry the same values, on errors too. `model`, `answers` and `usage` keep the Jev shape, and the official `typesafe-sdk` ignores the extra field. `OPENJEV_RESPONSE_TIMING=false` removes it. [Field reference](./api#response-and-measurement)

## Where the time went

Previous version, balanced profile:

| Stage | Cost | Paid |
| --- | --- | --- |
| Chat template (`/apply-template`) | 9 ms at any content size | per request |
| Token count (`/tokenize`) | 0.6 ms for 150 tokens, 2.7 ms for 1,250 | per question, in turn |
| Shared state and images | read and encoded again | per additional question |
| Photo preparation in the API | 65 ms for 2048×1536, 119 ms for 4032×3024, then resized again by llama.cpp | per image |
| Prompt processing | 0.29 s for a 276-token ticket, 1.0 s for a 1.2k-token policy, 0.75 s for a 448×672 screenshot | per token and image |

Qwen3.5, Qwen3.6 and Qwen3.8 are hybrid models. Their recurrent layers cannot roll back to an arbitrary position, and llama.cpp checkpoints only near the end of each prompt, so every further question re-read the whole state: `forcing full prompt re-processing due to lack of cache data`.

## What changed

**Prefix priming.** A request with several questions evaluates the shared prefix once. Each question resumes from that checkpoint and reads only its own text. Usage still counts every question's full prompt.

**Template skeleton.** The Qwen template wraps each user or system message in fixed text. The API renders that frame once, checks its first results against llama.cpp and then fills it locally, saving a backend call on every request. Assistant and tool messages, and content with unusual edge whitespace, still go to llama.cpp.

**Parallel token counts.** The shared prefix is counted once, the questions in parallel.

**One resize per image.** An oversized image goes straight to the vision encoder's size on its 32 px grid, instead of being resized twice. Large JPEGs decode at reduced scale: API-side preparation drops to 31 ms for 2048×1536 and 55 ms for 4032×3024.

## Repeated state

When consecutive requests repeat a state with new questions, the API keeps a checkpoint right after the state, and each request reads only its question. OpenJev's [llama.cpp patch](./models#max-qwen3-8-27b) goes one step further: it places that checkpoint exactly at the end of the state, and it lets a request skip the extra pass llama.cpp otherwise spends to checkpoint the end of every prompt.

| Qwen3.8-27B, compact Tetris prompt | Median per decision |
| --- | ---: |
| Stock llama.cpp | 1.93 s |
| With the repeated-state cache | 0.83 s |
| With the cache and the patch | 0.66 s |

Sixteen decisions per setup, one server at a time ([receipts](https://github.com/jev-skills/openjev-multimodal/tree/main/examples/tetris/report/probes)). All 32 answers of a fixed check set matched stock llama.cpp. `OPENJEV_PRIME_REPEATED_STATE=false` turns the cache off.

Several states can take turns. The llama.cpp that `scripts/build-llama.sh` builds keeps earlier prompts in memory with their checkpoints, so four 800-token states used in rotation each answered in 0.11 s on Qwen3.5-4B, against 0.69 s with llama.cpp b9670, which re-read every state.

## Browser agents

A browser agent sends each page as JSON, with a dozen questions on every turn. `page_12q` in `scripts/latency.py` is such a turn: a 112-node checkout page and 12 questions.

- **Compact JSON.** JSON states now reach the model without spaces after `,` and `:`. The page takes 22% fewer tokens, and the turn took 10.1 s instead of 12.2 s on Qwen3.5-4B. Decisions were identical except on one question that was already close, what the chosen step will change (0.41 against 0.56). `OPENJEV_COMPACT_JSON=false` restores the spaced form, which the tables above used.
- **Checkpoints every 512 tokens.** OpenJev's llama.cpp build now checkpoints each prompt along the way, so a follow-up that shares only the start of a state resumes near where the two differ. The same page without its history took 0.65 s instead of 3.61 s; the next turn after filling one field, 8.66 s instead of 9.65 s. Answers were identical.
- **Ask later, not every turn.** A request with the identical state reads only its new questions: one more question about the page took 0.27 s. Questions that are rarely needed belong in a follow-up.

Medians of 7 interleaved trials on one llama.cpp process, cleared before each request (`--flush`), while another app kept the GPU busy: compare within a line. Receipts: [compact JSON](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/json-states.json) · [checkpoints](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/checkpoints.json)

## Accuracy

Every trial sends the identical request to both versions.

- **Decisions:** the same in all 224 pairs (4 profiles × 8 requests × 7 trials).
- **One question, no large image:** identical probabilities.
- **Several questions:** probabilities within 0.001 on the 0.8B, 4B and 27B models, within 0.067 on 35B-A3B. The prefix now runs as its own batch, which changes the floating-point summation order.
- **Photos:** within 0.018, from one resampling instead of two.

## Next

- Batch the questions of one request from the shared checkpoint.
- Label-prior calibration and multi-token option scoring, evaluated on their own because they change probabilities.
- Continuous batching across requests, for throughput.
- A trained readout, such as LoRA or distillation from the quality profile, once labeled decisions exist.

## Method

`scripts/latency.py` sends each new request to both versions in rotating order. Each version runs its own llama.cpp process, so neither answers from the other's cache. A fresh identifier opens every state, so every request starts cold; the repeat case times the second of two identical requests. Seven trials per request after two warm-ups, on an M3 Max (128 GB) with llama.cpp b9670, September 21, 2026. max kept one model in memory: both versions shared one llama.cpp process, cleared before each request (`--flush`), with 30 s of idle before each trial, on September 22. No sample overlapped other inference.

```bash
uv run python scripts/latency.py --quiet --output benchmarks/performance/balanced.json \
  before=http://127.0.0.1:8101 after=http://127.0.0.1:8100
uv run python scripts/render_performance.py --chart
```

Receipts: [fast](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/fast.json) · [balanced](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/balanced.json) · [quality](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/quality.json) · [max](https://github.com/jev-skills/openjev-multimodal/blob/main/benchmarks/performance/max.json)

<style scoped>
.delta { margin-left: 6px; font-size: 12px; color: var(--vp-c-text-3); white-space: nowrap; }
.model { margin-left: 4px; font-weight: 400; color: var(--vp-c-text-3); }
.latency td, .latency th { white-space: nowrap; }
td { font-variant-numeric: tabular-nums; }
</style>
