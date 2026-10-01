"""The built-in backend: llama.cpp over localhost HTTP.

`openjev serve` fetches the profile's pinned GGUF weights and projector, launches
llama-server with one slot and reads label probabilities from /completion, including
labels outside the ordinary top-k. `--connect` uses a server that is already running.
"""

import asyncio
import itertools
import math
import os
import shutil
import socket
import string
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import Settings
from ..errors import APIError
from ..fetch import SOURCES, cached, fetch
from ..profiles import PROFILES
from . import BackendPlugin, Readout

# The build from scripts/build-llama.sh, with OpenJev's checkpoint controls.
PATCHED = Path(__file__).resolve().parents[3] / ".llamacpp/llama.cpp/build/bin/llama-server"

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


class LlamaBackend:
    name = "llama.cpp"
    prime_single = False  # priming one question would only add a round trip

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
        self.weights: str | None = None  # the loaded weights file, reported by /health
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
        self.weights = Path(props["model_path"]).name if props.get("model_path") else None
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

        Hybrid recurrent models (Qwen3.5, 3.6, 3.8) cannot roll back to an arbitrary cached
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


def default_llama_server() -> str:
    """OPENJEV_LLAMA_SERVER, else the build from scripts/build-llama.sh, else PATH."""
    if configured := os.environ.get("OPENJEV_LLAMA_SERVER"):
        return configured
    return str(PATCHED) if PATCHED.is_file() else "llama-server"


def weights(
    profile, model_file=None, mmproj_file=None, source="huggingface", connections=8, quant=None
):
    """Local paths to the profile's weights and projector, downloading what is missing."""
    paths = []
    artifacts = profile.artifacts(quant)
    for supplied, artifact in zip((model_file, mmproj_file), artifacts, strict=True):
        if supplied is not None:
            path = supplied.expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"Missing model file: {path}")
            paths.append(str(path))
        else:
            if not cached(artifact):
                print(f"Preparing {artifact.repo}/{artifact.filename} from {source} …", flush=True)
            path = fetch(artifact, source, connections, log=lambda line: print(line, flush=True))
            paths.append(str(path))
    return paths


class LlamaCpp(BackendPlugin):
    name = LlamaBackend.name
    summary = "llama.cpp server with pinned GGUF weights"
    profiles = {name: profile.model for name, profile in PROFILES.items()}

    def add_arguments(self, parser, command):
        options = parser.add_argument_group("llama.cpp backend")
        if command == "serve":
            options.add_argument("--backend-port", type=int, default=18081)
            options.add_argument(
                "--connect", help="Connect to an existing llama.cpp server instead of launching"
            )
            options.add_argument("--model-file", type=Path, help="Use existing GGUF weights")
            options.add_argument(
                "--mmproj-file", type=Path, help="Use existing matching vision projector"
            )
            options.add_argument(
                "--llama-server",
                default=default_llama_server(),
                help="llama-server binary (default: OpenJev's patched build when built, else PATH)",
            )
            options.add_argument(
                "--threads", type=int, default=4, help="Bound CPU threads (default: 4)"
            )
            options.add_argument("--startup-timeout", type=float, default=300)
        options.add_argument(
            "--source",
            choices=SOURCES,
            default=os.environ.get("OPENJEV_MODEL_SOURCE", "huggingface"),
            help="hub to download missing weights from; the other one is the fallback",
        )
        options.add_argument(
            "--connections", type=int, default=8, help="parallel downloads per file (default: 8)"
        )
        options.add_argument("--quant", help="another pinned quantization, e.g. Q8_0 for max")

    def create(self, settings):
        return LlamaBackend(settings)

    @contextmanager
    def launch(self, args, settings) -> Iterator[LlamaBackend]:
        url = args.connect or f"http://127.0.0.1:{args.backend_port}"
        settings = settings.model_copy(update={"backend_url": url})
        if args.connect:
            yield LlamaBackend(settings)
            return
        executable = shutil.which(args.llama_server)
        if not executable:
            raise ValueError("llama-server is missing. On macOS run: brew install llama.cpp")
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", args.backend_port)) == 0:
                raise ValueError(
                    f"Backend port {args.backend_port} is occupied; "
                    "use --connect or choose --backend-port."
                )
        profile = PROFILES[args.profile]
        model, projector = weights(
            profile, args.model_file, args.mmproj_file, args.source, args.connections, args.quant
        )
        logs = Path.home() / ".cache" / "openjev-multimodal"
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / f"backend-{args.backend_port}.log"
        command = [
            executable,
            "-m",
            model,
            "--mmproj",
            projector,
            "--host",
            "127.0.0.1",
            "--port",
            str(args.backend_port),
            "--alias",
            profile.model,
            "-c",
            str(settings.max_input_tokens),
            "-np",
            "1",
            "-ngl",
            "99",
            "--jinja",
            "--reasoning",
            "off",
            "--chat-template-kwargs",
            '{"enable_thinking":false}',
            "--image-max-tokens",
            str(settings.image_token_budget),
            "-t",
            str(args.threads),
            "-tb",
            str(args.threads),
        ]
        with log_path.open("a") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                print(f"Loading {profile.model} on Metal. Backend log: {log_path}", flush=True)
                deadline = time.monotonic() + args.startup_timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"llama-server exited ({process.returncode}); see {log_path}"
                        )
                    try:
                        with httpx.Client(timeout=1, trust_env=False) as client:
                            if client.get(url + "/health").status_code == 200:
                                break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(f"Model startup timed out; see {log_path}")
                yield LlamaBackend(settings)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    def download(self, args):
        return weights(
            PROFILES[args.profile],
            source=args.source,
            connections=args.connections,
            quant=args.quant,
        )

    def doctor(self):
        return {"llama_server": shutil.which(default_llama_server())}


plugin = LlamaCpp()
