"""llama.cpp single-token readout, including selected labels outside ordinary top-k."""

import asyncio
import itertools
import math
import string
from dataclasses import dataclass

import httpx

from .config import Settings
from .errors import APIError


@dataclass
class Readout:
    probabilities: list[float]
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    inference_ms: float


class LlamaBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {}
        if settings.backend_api_key:
            headers["Authorization"] = f"Bearer {settings.backend_api_key.get_secret_value()}"
        self.client = httpx.AsyncClient(
            base_url=settings.backend_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(settings.request_timeout, connect=3),
            limits=httpx.Limits(max_connections=16),
            trust_env=False,
        )
        self.labels: list[tuple[str, int]] = []
        self.model = settings.model_name
        self.vision = False
        self.media_marker = "<__media__>"
        self.context_size = settings.max_input_tokens

    async def close(self):
        await self.client.aclose()

    async def call(self, path: str, payload=None):
        try:
            response = (
                await self.client.get(path)
                if payload is None
                else await self.client.post(path, json=payload)
            )
            if response.status_code >= 400:
                if response.status_code in {400, 413}:
                    raise APIError("Backend rejected the prompt; check context and image limits.")
                raise APIError("Inference backend is unavailable.", 503)
            return response.json()
        except httpx.TimeoutException as exc:
            raise APIError("Inference deadline exceeded.", 504) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError("Cannot reach a valid llama.cpp backend.", 503) from exc

    async def ready(self) -> bool:
        try:
            data = await self.call("/health")
            return data.get("status") == "ok"
        except APIError:
            return False

    async def tokenize(self, value: str) -> list[int]:
        data = await self.call(
            "/tokenize",
            {
                "content": value,
                "add_special": False,
                "parse_special": True,
            },
        )
        return data["tokens"]

    async def initialize(self):
        catalog = await self.call("/v1/models")
        props = await self.call("/props")
        self.media_marker = props.get("media_marker", self.media_marker)
        try:
            self.model = catalog["data"][0]["id"]
            self.context_size = min(
                self.settings.max_input_tokens,
                catalog["data"][0].get("meta", {}).get("n_ctx", self.settings.max_input_tokens),
            )
            self.vision = "multimodal" in catalog["models"][0].get("capabilities", [])
        except (KeyError, IndexError, TypeError) as exc:
            raise APIError(
                "Backend model catalogue is incompatible; use llama.cpp b9670+.", 503
            ) from exc
        candidates = list(string.ascii_uppercase) + [
            "".join(x) for x in itertools.product(string.ascii_uppercase, repeat=2)
        ]
        for start in range(0, len(candidates), 16):
            batch = candidates[start : start + 16]
            encoded = await asyncio.gather(*(self.tokenize(label) for label in batch))
            for label, ids in zip(batch, encoded, strict=True):
                if len(ids) == 1 and ids[0] not in {x[1] for x in self.labels}:
                    decoded = await self.call("/detokenize", {"tokens": ids})
                    if decoded.get("content") == label:
                        self.labels.append((label, ids[0]))
                if len(self.labels) == 64:
                    return
        raise APIError("The backend needs 64 distinct single-token answer labels.", 503)

    async def template(self, messages: list[dict]) -> str:
        data = await self.call(
            "/apply-template",
            {
                "messages": messages,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        if not isinstance(data.get("prompt"), str):
            raise APIError("Backend returned no chat template.", 502)
        return data["prompt"]

    async def read(self, prompt: str, images: list[str], labels: list[tuple[str, int]]) -> Readout:
        prompt = prompt.replace("<__media__>", self.media_marker)
        # Adding the SAME bias to all label logits preserves their pairwise odds.
        # Post-sampling probabilities include this bias; normalizing over labels
        # cancels it. The completeness check prevents silent top-k truncation.
        payload = {
            "prompt": {"prompt_string": prompt, "multimodal_data": images} if images else prompt,
            "n_predict": 1,
            "temperature": 1.0,
            "samplers": ["temperature"],
            "top_k": 0,
            "top_p": 1.0,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "logit_bias": [[token, 100.0] for _, token in labels],
            "n_probs": len(labels),
            "post_sampling_probs": True,
            "cache_prompt": True,
            "id_slot": 0,
        }
        result = await self.call("/completion", payload)
        try:
            items = result["completion_probabilities"][0]["top_probs"]
            table = {item["id"]: item["prob"] for item in items}
            raw = [table[token] for _, token in labels]
            if not all(isinstance(p, (float, int)) and math.isfinite(p) and p >= 0 for p in raw):
                raise ValueError("Invalid probabilities")
            total = math.fsum(raw)
            if total <= 0 or result.get("truncated") or result["tokens_predicted"] != 1:
                raise ValueError("Invalid readout")
            timing = result["timings"]
            return Readout(
                probabilities=[p / total for p in raw],
                input_tokens=result["tokens_evaluated"],
                output_tokens=result["tokens_predicted"],
                cached_tokens=timing["cache_n"],
                inference_ms=timing["prompt_ms"] + timing["predicted_ms"],
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise APIError(
                "Backend did not return every label probability or truncated the prompt. "
                "Use llama.cpp b9670+ with post_sampling_probs support.",
                502,
            ) from exc
