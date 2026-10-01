"""Inference backends: what the API needs from an engine, and how engines plug in.

A backend answers every question with one output token: the probability of each option
label after a prompt. OpenJev ships the llama.cpp backend. A Python package adds another by
exposing a `BackendPlugin` under the `openjev.backends` entry-point group:

    [project.entry-points."openjev.backends"]
    mine = "my_package:plugin"

Installed next to OpenJev, it runs with `openjev serve --backend mine` or
`OPENJEV_BACKEND=mine`.
"""

import argparse
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Protocol

from ..config import Settings

GROUP = "openjev.backends"
DEFAULT = "llama.cpp"
BUILTIN = (EntryPoint(DEFAULT, "openjev.backends.llamacpp:plugin", GROUP),)


@dataclass
class Readout:
    """One question's answer and what reading it cost."""

    probabilities: list[float]  # one per label, in label order, summing to 1
    input_tokens: int
    output_tokens: int
    cached_tokens: int  # prompt tokens reused instead of evaluated
    inference_ms: float  # model time the backend reports


class Backend(Protocol):
    """One loaded model behind the API.

    Prompts are rendered chat-template text in which each image is `<__media__>`; the images
    follow in the same order as base64 strings.
    """

    name: str  # reported by /health as "backend"
    model: str
    vision: bool
    context_size: int  # prompt tokens one question may use
    labels: list[tuple[str, int]]  # 255 single-token answer labels, set by initialize()
    build: str | None  # engine build or version, reported as "backend_build"
    weights: str | None  # loaded weights, reported as "weights"
    # Prime single-question requests too: true when the backend keeps its own prefix
    # snapshots, so priming costs nothing extra and a later request can reuse the state.
    prime_single: bool

    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def ready(self) -> bool: ...

    async def template(self, messages: list[dict]) -> str:
        """The chat template for `messages`, with the generation prompt and thinking off."""
        ...

    async def tokenize(self, value: str) -> list[int]: ...

    async def prime(self, prefix: str, images: list[str]) -> None:
        """Evaluate the prefix shared by the reads that follow, so they resume after it."""
        ...

    async def read(
        self,
        prompt: str,
        images: list[str],
        labels: list[tuple[str, int]],
        checkpoints: bool = True,
    ) -> Readout:
        """Label probabilities after `prompt`; `checkpoints=False`: its end is not reused."""
        ...

    # Optional: `async def read_many(prompts, images, labels) -> list[Readout]` reads prompts
    # that all extend the primed prefix together. `read_all` falls back to one read at a time.


class BackendPlugin:
    """How `openjev serve` and `openjev download` run one backend."""

    name = ""
    summary = ""  # one line for `openjev doctor`
    profiles: Mapping[str, str] = {}  # profile name -> model ID
    default_profile = "balanced"

    def add_arguments(self, parser: argparse.ArgumentParser, command: str) -> None:
        """Add this backend's options to the `serve` or `download` command."""

    def create(self, settings: Settings) -> Backend:
        """A backend for `settings` that downloads and launches nothing."""
        raise NotImplementedError

    @contextmanager
    def launch(self, args: argparse.Namespace, settings: Settings) -> Iterator[Backend]:
        """Prepare weights and helper processes for `serve`, yield the backend, clean up."""
        yield self.create(settings)

    def download(self, args: argparse.Namespace) -> list[str]:
        """Cache the weights that `args` select and return their local paths."""
        raise ValueError(f"The {self.name} backend has nothing to download.")

    def doctor(self) -> dict:
        """Prerequisites for `openjev doctor`, checked without downloading anything."""
        return {}


async def read_all(
    backend: Backend, prompts: list[str], images: list[str], labels: list[list[tuple[str, int]]]
) -> list[Readout]:
    """Read prompts that extend the primed prefix, together when the backend can."""
    if many := getattr(backend, "read_many", None):
        return await many(prompts, images, labels)
    return [
        await backend.read(prompt, images, label, checkpoints=False)
        for prompt, label in zip(prompts, labels, strict=True)
    ]


def normalized(name: str) -> str:
    """Names match without case or punctuation: llama.cpp, llamacpp and LLaMA-CPP agree."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def registered() -> dict[str, EntryPoint]:
    """Installed backends by normalized name; the built-in one comes first and wins."""
    found: dict[str, EntryPoint] = {}
    for point in (*BUILTIN, *entry_points(group=GROUP)):
        found.setdefault(normalized(point.name), point)
    return found


def names() -> list[str]:
    return [point.name for point in registered().values()]


def load(name: str) -> BackendPlugin:
    point = registered().get(normalized(name))
    if point is None:
        raise ValueError(f"Unknown backend {name!r}; installed: {', '.join(names())}")
    try:
        plugin = point.load()
    except Exception as exc:  # a broken plugin package must not take the CLI down with it
        raise ValueError(f"Backend {point.name!r} failed to load: {exc}") from exc
    return plugin() if isinstance(plugin, type) else plugin
