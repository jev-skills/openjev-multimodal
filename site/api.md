---
title: SystemOne API reference — Noul, Choice and Score
description: Jev-compatible schemas, multimodal image inputs, probability semantics, authentication, limits and error codes.
---

# API reference

Base URL: `http://127.0.0.1:8000`. Requests and responses use JSON. If `OPENJEV_API_KEY` is configured, send `Authorization: Bearer YOUR_KEY` to `/v1/*`.

## POST /v1/systemone

| Field | Type | Meaning |
| --- | --- | --- |
| `model` | string | `jev-latest`, `openjev-latest`, or active ID; defaults to `jev-latest` |
| `state` | string, object or array | Shared content to evaluate |
| `questions` | object | 1–64 named questions |
| `images` | string array | Optional extension: up to 8 PNG/JPEG/WebP data URLs |

State accepts ordinary JSON, an array of chat messages, or exactly `{"messages": [...]}`. Chat content may be text or OpenAI-style `text` / `image_url` parts. An object with `messages` **and other fields** remains intact as JSON so metadata is preserved.

Instructions and criterion descriptions may be strings, objects or arrays. Structured values are serialized intact. Question IDs are response keys and are not shown to the model. Choice keys are hidden unless their description is `null`.

## Noul — probability of yes

```json
{
  "type": "noul",
  "instructions": "Does the customer request a refund?",
  "criteria": { "true": "A refund is requested", "false": "No refund is requested" }
}
```

Criteria are optional and default to Yes / No. Result:

```ts
{ type: "noul"; noul: number } // 0–1, probability of the true criterion
```

A value near 0.5 means uncertainty between alternatives, not medium intensity.

## Choice — one option and its distribution

```json
{
  "type": "choice",
  "instructions": "Which team should handle this?",
  "criteria": {
    "billing": { "covers": ["Payments", "Refunds"] },
    "technical": "Software bugs",
    "other": null
  }
}
```

Provide 2–255 options. Result:

```ts
{
  type: "choice";
  choice: string;                         // original option key
  probabilities: Record<string, number>;  // every option; sums to 1
  confidence: number;                     // 0–1
}
```

## Score — expected rubric position

```json
{
  "type": "score",
  "instructions": "How urgent is this request?",
  "criteria": ["Routine", "Urgent", "Emergency"]
}
```

Provide 2–64 ordered levels, lowest to highest. Indices start at zero.

```ts
{
  type: "score";
  score: number; // sum(index * probability); between 0 and levels - 1
  legend: Record<string, string>;
  probabilities: Record<string, number>;
  confidence: number;
}
```

Structured rubric descriptions are JSON strings in `legend`.

## Response and measurement

```ts
{
  model: string; // requested alias or ID
  answers: Record<string, NoulAnswer | ChoiceAnswer | ScoreAnswer>;
  usage: { input_tokens: number; output_tokens: number };
  timing?: {                // OpenJev extension, milliseconds
    processing_ms: number;  // request received → response ready, on the server
    parse_ms: number;       // read, decode and validate the request
    prepare_ms: number;     // state, images and prompt compilation
    queue_ms: number;       // waiting for the inference slot
    inference_ms: number;   // prefix priming and one readout per question
  };
}
```

Input usage sums full backend prompt counts across questions, including image and cached tokens. Output usage is the number of questions. These are local backend counts, not TypeSafe billing units.

`timing` answers "how long did the server take?" without client-side instrumentation: `processing_ms` runs from the moment the API receives the request until the response is ready, and excludes network transfer. The stages add up to it within a fraction of a millisecond. `model`, `answers` and `usage` keep the exact Jev shape: the official Python SDK parses responses with `extra="ignore"` and the JavaScript SDK returns parsed JSON, so both skip the extra field. For clients that reject unknown fields, set `OPENJEV_RESPONSE_TIMING=false`; the headers below still carry the same numbers.

| Header | Meaning |
| --- | --- |
| `x-typesafe-request-id` | Unique request ID |
| `x-openjev-model` | Actual backend model |
| `x-openjev-cached-tokens` | Backend-reported reused tokens |
| `x-openjev-processing-ms` | Server processing time; also sent on every `/v1/*` error |
| `x-openjev-elapsed-ms` | Evaluation time, from state preparation to the last readout |
| `Server-Timing` | `parse`, `prepare`, `queue`, `inference`, `total`, plus `compute` (model time reported by llama.cpp) |

`Server-Timing` appears in the browser developer tools' timing view.

Probability is conditioned on supplied options. Confidence is `1 − H(p)/log(n)`, measuring concentration. Neither promises calibrated correctness.

## Discovery and health

| Route | Purpose |
| --- | --- |
| `GET /v1/models` | TypeSafe-style and OpenAI-style catalogues |
| `GET /v1/limits` | Configured admission limits |
| `GET /health` | Checks the backend and reports its name, model, weights file and build; 503 when unavailable |
| `GET /health/live` | API process liveness |
| `GET /docs` | Interactive OpenAPI reference |
| `GET /openapi.json` | Machine-readable schema |
| `GET /playground` | Local text/image demo |

Defaults: 16 MiB request body; 8,192 estimated tokens per branch including output; 131,072 total input tokens; 8 images; 20 million decoded pixels per image; 1,024-pixel longest edge; 120-second deadline. Image-token admission is conservative; the backend enforces actual context too.

## Errors

```json
{ "error": { "message": "Human-readable error" } }
```

| Status | Meaning |
| --- | --- |
| `401` | Missing or invalid API key |
| `413` | Body or decoded image too large |
| `422` | Invalid schema/image, unknown model, unsupported modality or token limit |
| `502` | Incomplete probability readout or incompatible backend |
| `503` | Backend unavailable |
| `504` | Evaluation deadline exceeded |
| `529` | Admission queue full; use `Retry-After` |

Validation errors include field locations without echoing private input.
