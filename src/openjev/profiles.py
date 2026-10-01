from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    model: str
    repo: str
    revision: str
    weights: str
    projector: str = "mmproj-F16.gguf"
    projector_repo: str | None = None
    projector_revision: str | None = None


PROFILES = {
    "fast": Profile(
        "Qwen/Qwen3.5-0.8B",
        "unsloth/Qwen3.5-0.8B-GGUF",
        "6ab461498e2023f6e3c1baea90a8f0fe38ab64d0",
        "Qwen3.5-0.8B-Q4_K_M.gguf",
    ),
    "balanced": Profile(
        "Qwen/Qwen3.5-4B",
        "unsloth/Qwen3.5-4B-GGUF",
        "e87f176479d0855a907a41277aca2f8ee7a09523",
        "Qwen3.5-4B-Q4_K_M.gguf",
    ),
    "quality": Profile(
        "Qwen/Qwen3.6-35B-A3B",
        "havenoammo/Qwen3.6-35B-A3B-MTP-GGUF",
        "a529a1734ce45a423a27a399d462791201d6995b",
        "Qwen3.6-35B-A3B-MTP-UD-Q4_K_XL.gguf",
        projector_repo="unsloth/Qwen3.6-35B-A3B-GGUF",
        projector_revision="a483e9e6cbd595906af30beda3187c2663a1118c",
    ),
    "max": Profile(
        "Qwen/Qwen3.8-27B",
        "unsloth/Qwen3.8-27B-GGUF",
        "4ca720788d1e01f1bff70c033e0d0028fd02e502",
        "Qwen3.8-27B-UD-Q4_K_XL.gguf",
    ),
}
