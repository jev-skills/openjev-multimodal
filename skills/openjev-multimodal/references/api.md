# OpenJev Multimodal API

Base URL `http://127.0.0.1:8000`, JSON in and out. With `OPENJEV_API_KEY` set on the
server, send `Authorization: Bearer <key>` to every `/v1/*` route. The live schema is at
`/openapi.json` and `/docs`; the numbers below are the defaults, so read `/v1/limits`
for the running server.

## POST /v1/systemone

| Field | Type | Meaning |
| --- | --- | --- |
| `model` | string | `jev-latest`, `openjev-latest` or the loaded model ID; default `jev-latest` |
| `state` | string, object or array | What the questions are about |
| `questions` | object | 1–64 named questions, each answered independently |
| `images` | array of strings | Up to 8 inline data URLs: `data:image/png;base64,…` (PNG, JPEG, WebP) |

`state` may be plain text, any JSON value, an array of chat messages, or exactly
`{"messages": [...]}`. Chat messages may carry OpenAI-style content parts
(`{"type": "text"}` and `{"type": "image_url", "image_url": {"url": "data:…"}}`). An
object with `messages` and other keys is kept as JSON so the metadata survives.

Instructions and criteria may be strings, objects or arrays; structured values are
passed through as JSON. Question IDs are only response keys. Choice keys are shown to
the model only when their description is `null`.

### Question types

```jsonc
{"type": "noul", "instructions": "Does the customer ask for a refund?",
 "criteria": {"true": "A refund is requested", "false": "No refund is requested"}}  // criteria optional

{"type": "choice", "instructions": "Which team should handle this?",
 "criteria": {"billing": "Payments and refunds", "technical": "Software bugs", "other": null}}  // 2–255

{"type": "score", "instructions": "How urgent is this request?",
 "criteria": ["Routine", "Needs attention today", "Service is down"]}  // 2–64, lowest first
```

### Answers

```ts
{ type: "noul";   noul: number }                                   // P(true criterion)
{ type: "choice"; choice: string; probabilities: Record<string, number>; confidence: number }
{ type: "score";  score: number; legend: Record<string, string>;
  probabilities: Record<string, number>; confidence: number }        // score = Σ index × p
```

The response is `{model, answers, usage: {input_tokens, output_tokens}}`; output tokens
equal the number of questions. Probabilities sum to 1 over the supplied options.
Confidence is `1 − H(p) / log(n)`, a measure of concentration.

### Response headers

| Header | Meaning |
| --- | --- |
| `x-openjev-elapsed-ms` | Evaluation time on the server |
| `Server-Timing` | `prepare`, `queue` and `inference` durations |
| `x-openjev-cached-tokens` | Prompt tokens the backend reused |
| `x-openjev-model` | Model that actually answered |
| `x-typesafe-request-id` | Unique request ID |

## Other routes

| Route | Use |
| --- | --- |
| `GET /health` | Backend readiness, backend name, model name and whether images are supported; 503 when not ready |
| `GET /health/live` | The API process is up |
| `GET /v1/models` | Accepted model IDs (TypeSafe-style and OpenAI-style lists) |
| `GET /v1/limits` | Options, levels, questions, images, image edge, token and time limits |
| `GET /playground` | Local page for trying text and images |

## Defaults and limits

16 MiB request body · 8,192 context tokens per question · 131,072 input tokens per
request · 8 images, each at most 20 million decoded pixels and resized to a 1,024 px
longest edge · 512 visual tokens per image in the backend · 120 s deadline including
queue time · one inference slot with up to 4 requests admitted.

## Errors

Errors are `{"error": {"message": "…"}}`; validation errors add `detail` with field
locations, without echoing private input.

| Status | Meaning | What to do |
| --- | --- | --- |
| 401 | Missing or wrong API key | Send the Bearer key |
| 413 | Body or decoded image too large | Shrink or crop the image |
| 422 | Invalid schema or image, unknown model, image on a text-only backend, token limit | Fix the request |
| 502 | Incomplete probability readout or incompatible backend | Use llama.cpp b9670+ |
| 503 | Backend not ready | Wait for `/health`, then retry |
| 504 | Deadline exceeded | Shorten the prompt or raise `OPENJEV_REQUEST_TIMEOUT` |
| 529 | Admission queue full | Retry after `Retry-After` |

## Python without dependencies

```python
import base64, json, urllib.request

image = base64.b64encode(open("screen.png", "rb").read()).decode()
body = {
    "model": "jev-latest",
    "state": "Read the attached checkout screen.",
    "images": ["data:image/png;base64," + image],
    "questions": {
        "status": {
            "type": "choice",
            "instructions": "What payment status is shown?",
            "criteria": {
                "paid": "Payment succeeded",
                "failed": "Payment failed",
                "other": "Something else",
            },
        }
    },
}
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/systemone",
    json.dumps(body).encode(),
    {"Content-Type": "application/json"},
)
answer = json.load(urllib.request.urlopen(request, timeout=120))["answers"]["status"]
print(answer["choice"], answer["probabilities"])
```
