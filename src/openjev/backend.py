"""llama.cpp single-token readout, including selected labels outside ordinary top-k."""

import asyncio
import itertools
import math
import string
import uuid
from dataclasses import dataclass

import httpx

from .config import Settings
from .errors import APIError

# Characters the chat-template `trim` filter removes. Content whose edges hold any other
# whitespace is always rendered by the backend, so the skeleton never guesses.
_TRIM = " \t\n\r"
_VERIFICATIONS = 3  # renders compared against the backend before a skeleton is trusted


@dataclass
class _Skeleton:
    parts: list[str]
    verified: int = 0


def _trimmed(content: str) -> str | None:
    value = content.strip(_TRIM)
    if value and (value[0].isspace() or value[-1].isspace()):
        return None
    return value


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
        self.build: str | None = None  # llama.cpp build_info, reported by /health
        self.media_marker = "<__media__>"
        self.context_size = settings.max_input_tokens
        self.skeletons: dict[tuple[str, ...], _Skeleton | None] = {}

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
        self.build = props.get("build_info")
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
                if len(self.labels) == 255:
                    return
        raise APIError("The backend needs 255 distinct single-token answer labels.", 503)

    async def render(self, messages: list[dict]) -> str:
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

    async def template(self, messages: list[dict]) -> str:
        """Render the chat template, reusing a verified skeleton when one applies.

        llama.cpp's /apply-template prepares a complete chat request on every call (render,
        output parser and grammar setup): about 9 ms whatever the content size. For
        conversations of only user and system text messages, the template emits fixed text
        around each trimmed message, so a skeleton rendered once with sentinel contents
        reproduces it exactly. The first renders are still compared with the backend; any
        mismatch disables the skeleton for good.
        """
        roles = tuple(m["role"] for m in messages)
        cacheable = (
            self.settings.template_cache
            and all(isinstance(m.get("content"), str) and len(m) == 2 for m in messages)
            and all(role == "user" or (role == "system" and i == 0) for i, role in enumerate(roles))
        )
        if not cacheable:
            return await self.render(messages)
        if roles not in self.skeletons:
            self.skeletons[roles] = await self._skeleton(roles)
        skeleton = self.skeletons[roles]
        contents = [_trimmed(m["content"]) for m in messages]
        if skeleton is None or None in contents:
            return await self.render(messages)
        rendered = skeleton.parts[0] + "".join(
            content + part for content, part in zip(contents, skeleton.parts[1:], strict=True)
        )
        if skeleton.verified < _VERIFICATIONS:
            actual = await self.render(messages)
            if actual != rendered:
                self.skeletons[roles] = None
                return actual
            skeleton.verified += 1
        return rendered

    async def _skeleton(self, roles: tuple[str, ...]) -> _Skeleton | None:
        sentinels = [f"OPENJEV{uuid.uuid4().hex}S{i}" for i in range(len(roles))]
        try:
            rendered = await self.render(
                [{"role": role, "content": s} for role, s in zip(roles, sentinels, strict=True)]
            )
        except APIError:
            return None
        parts, rest = [], rendered
        for sentinel in sentinels:
            if rest.count(sentinel) != 1:
                return None
            head, rest = rest.split(sentinel)
            parts.append(head)
        return _Skeleton(parts + [rest])

    async def prime(self, prefix: str, images: list[str]) -> None:
        """Evaluate only the prefix shared by all questions of a request.

        Hybrid recurrent models (Qwen3.5/3.6) cannot roll back to an arbitrary cached
        position, so without this every question re-reads the state and re-encodes images.
        llama.cpp checkpoints a few tokens before the end of each prompt; after this call,
        each question restores that checkpoint and processes only its own text.
        """
        prompt = prefix.replace("<__media__>", self.media_marker)
        payload = {"prompt_string": prompt, "multimodal_data": images} if images else prompt
        # checkpoint_end (OpenJev's llama.cpp build) places the checkpoint after the last prefix
        # token instead of a few tokens earlier, so questions re-read nothing; others ignore it.
        await self.call(
            "/completion",
            {
                "prompt": payload,
                "n_predict": 0,
                "cache_prompt": True,
                "id_slot": 0,
                "checkpoint_end": True,
            },
        )

    async def read(
        self,
        prompt: str,
        images: list[str],
        labels: list[tuple[str, int]],
        checkpoints: bool = True,
    ) -> Readout:
        """Read the label distribution after `prompt`.

        With `checkpoints=False` the backend skips the extra pass that hybrid models spend to
        checkpoint the end of a prompt (llama.cpp with OpenJev's `ctx_checkpoints` option;
        other builds ignore the field). Use it when the prompt resumes from a primed state
        and its own end will not be reused.
        """
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
        if not checkpoints:
            payload["ctx_checkpoints"] = False
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
