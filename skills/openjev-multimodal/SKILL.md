---
name: openjev-multimodal
description: Run and build with OpenJev Multimodal, a local Jev-compatible SystemOne API that turns text, screenshots and video frames into typed decisions (Noul, Choice, Score) with one output token per question on Apple Silicon. Use when an app needs a fast local judgment it can act on, such as routing a message, reading a screen, choosing the next UI or game action from options that code enumerates, or scoring against a rubric; when replacing a prompt-and-parse LLM step with typed probabilities; or when starting, checking, tuning or benchmarking the local service.
license: MIT
---

# Build with OpenJev Multimodal

OpenJev Multimodal serves `POST /v1/systemone` on your Mac. A request carries **state**
(text, JSON, chat messages and up to eight images) and named **questions**. Every
question is answered by reading **one output token** over option labels, so the
response is a complete probability distribution rather than generated text. Code owns
the workflow; the model supplies the judgment that code cannot compute.

It is an independent open-model implementation of the Jev wire format: it runs
Qwen3.5, Qwen3.6 and Qwen3.8 locally and is not TypeSafe's proprietary Jev. Probabilities are
conditioned on the options you supply; they are not calibrated guarantees.

## Check or start the service

```bash
curl -s http://127.0.0.1:8000/health            # {"status":"ok","model":...,"multimodal":true}
python3 scripts/openjev.py health               # health plus /v1/limits
```

If nothing answers, start it from a clone of
[jev-skills/openjev-multimodal](https://github.com/jev-skills/openjev-multimodal) on Apple
Silicon (`brew install uv llama.cpp`, llama.cpp b9670 or newer):

```bash
uv sync --frozen
uv run openjev serve                     # balanced: Qwen3.5-4B, text + images
uv run openjev serve --profile fast      # Qwen3.5-0.8B: smallest and fastest
uv run openjev serve --profile quality   # Qwen3.6-35B-A3B: strong and quick, ~24 GB of weights
uv run openjev serve --profile max       # Qwen3.8-27B: most capable, dense, ~18 GB of weights
uv run openjev doctor                    # prerequisites, without downloading anything
```

Run one profile at a time. The first start downloads pinned weights. The API binds to
`127.0.0.1`; set `OPENJEV_API_KEY` to require a Bearer key on `/v1/*`. Before writing
code against it, read `GET /v1/limits` and `GET /v1/models` rather than assuming limits.

## Make a call

```bash
curl -s http://127.0.0.1:8000/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "jev-latest",
  "state": {"ticket": "I was charged twice for one order.", "plan": "business"},
  "questions": {
    "team": {"type": "choice", "instructions": "Which team should handle this ticket?",
             "criteria": {"billing": "Payments, refunds and invoices",
                          "technical": "Bugs and outages", "other": "Anything else"}},
    "refund": {"type": "noul", "instructions": "Does the customer ask for money back?"}
  }
}'
```

Read `answers.team.choice`, `answers.team.probabilities` and `answers.refund.noul`.
Images go in `images` as inline data URLs (PNG, JPEG or WebP); remote URLs and file
paths are rejected. The helper script builds requests from the command line:

```bash
python3 scripts/openjev.py ask --state "Checkout screen after paying" --image shot.png \
  --choice "What payment status is shown?" \
  --option paid="Payment succeeded" --option pending="Still processing" --option failed="Payment failed"
```

For the full contract (fields, answer types, headers, limits, errors) see
[references/api.md](references/api.md).

## Design the judgment

Choose the primitive by what the answer means:

| Need | Primitive | Returns |
| --- | --- | --- |
| Whether a condition holds | `noul` | probability of the true criterion |
| One of a defined set | `choice` (2–255 options) | chosen key, every option's probability, confidence |
| Position on an ordered rubric | `score` (2–64 levels, lowest first) | expected level index, distribution |

Give each question the **state** it needs, the judgment in **instructions**, and
self-contained meanings in **criteria**. Question IDs are never shown to the model,
and a choice key is shown only when its description is `null`, so put the meaning in
the text. Structured JSON works for instructions and criteria when definitions,
priorities or examples help.

**Select instead of generate.** When the answer is an action, have code enumerate the
legal candidates, measure what each would do, and ask Jev to choose. The model cannot
pick an option you did not list, and code can execute the choice exactly.

**Keep the choice small and fair.** Small models lean toward early labels when faced
with long, similar lists. Remove options that another option matches or beats on
every measured fact; this needs no weights and never discards a reasonable trade-off.
List the survivors in a neutral order, such as left to right or alphabetical, never by
your own ranking. Add a `none` or `other` option whenever nothing might fit.

**Put exact facts in words; use images for what words cannot carry.** Counts, rules
and measurements belong in the option text. Images carry layout, shape and visual
state. In the Tetris study, pictures alone were not enough for any model, while
facts plus a small picture of each option's outcome gave the lowest regret for every
model size.

**Ask only the questions you will use.** The API reads a request's state once and
resumes every question from a checkpoint, but each question still costs its own text and
a readout: a long option list costs as much as the same text in the state. A follow-up
request with the identical state reads only its new questions, so questions that are
rarely needed can wait for a second request instead of riding along on every turn.

More patterns, prompts and measured trade-offs: [references/design.md](references/design.md).

## Send images the encoder can read

- Qwen's vision encoder cuts images into 16 px patches and merges each 2 × 2 group
  into one token, so **32 px ≈ one visual token**. The API downsizes anything above
  1,024 px on its longest edge; the backend's default budget is 512 visual tokens
  per image (`--image-tokens`).
- Render purpose-built images when you control them: crop to what matters, draw
  crisp edges without anti-aliasing, and size them to multiples of 32 px.
- Label visual options with the letters OpenJev assigns in criteria order (A to Z, then
  two-letter labels such as AA and AB) so text and picture point at the same thing.
- Do not upscale. A larger image costs more tokens and latency without better
  decisions; test the smallest size that stays legible.
- For video, send a few sampled frames with timestamps in the state.

`python3 scripts/openjev.py image shot.png` reports the visual-token cost of a file.

## Latency and throughput

Each question costs one prompt pass plus one output token; prompt length, image
tokens and model size set the pace. Inspect `usage.input_tokens`, the
`x-openjev-elapsed-ms` and `Server-Timing` response headers, and cached tokens in
`x-openjev-cached-tokens`. Inference runs on one slot: concurrent requests queue, and
HTTP 529 means the queue is full, so retry after `Retry-After`. Measured on an Apple
M3 Max for a ~500-token decision with one small image: fast 0.15 s, balanced 0.65 s,
quality 0.91 s, max about 4 s. Keep whatever does not change in the state and send it
unchanged: the API caches a repeated state, so each request reads only its question.
For Qwen3.8-27B that took a Tetris decision from 1.9 s to 0.7 s (with the llama.cpp
patch from `scripts/build-llama.sh`).

## Use the probabilities

Act on a clear margin, and escalate or ask the user when the top options are close.
Choice and Score confidence is `1 − normalized entropy`: it measures how concentrated
the distribution is, not whether the answer is correct. A Noul near 0.5 means the two
outcomes are similarly likely, not a medium intensity. Choose thresholds on your own
data and consequences.

## Worked example

[`examples/tetris`](https://github.com/jev-skills/openjev-multimodal/tree/main/examples/tetris)
plays Tetris through the API. Code enumerates every two-piece plan, prunes dominated
ones, and sends one Choice with each plan's keys and measured result plus a lettered
image of the outcomes; Jev's single token picks the plan. It includes the benchmark
across all four profiles, a no-model baseline, a design study of image resolution,
replay videos and a browser game.

## Care

- Keep the service on localhost unless you add a key and TLS in front of it.
- State and images are prompts: text inside them can steer the answer. Treat answers
  as inputs to your code, not as authority.
- Validate on your own data before relying on a threshold. These are open models
  running locally, with different accuracy from TypeSafe's hosted Jev.
