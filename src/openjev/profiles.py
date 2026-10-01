from dataclasses import dataclass


@dataclass(frozen=True)
class Artifact:
    """One pinned file: where it lives and what its bytes must hash to."""

    repo: str
    revision: str
    filename: str
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Profile:
    model: str
    repo: str
    revision: str
    weights: str
    projector: str = "mmproj-F16.gguf"
    projector_repo: str | None = None
    projector_revision: str | None = None
    # (size in bytes, SHA-256) of the weights and the projector at the pinned revisions.
    weights_digest: tuple[int, str] | None = None
    projector_digest: tuple[int, str] | None = None
    # Other quantizations of the same model at the same revision: name -> (file, size, SHA-256).
    quants: tuple[tuple[str, str, int, str], ...] = ()

    def artifacts(self, quant: str | None = None) -> tuple[Artifact, Artifact]:
        if quant:
            match = next((q for q in self.quants if q[0] == quant), None)
            if match is None:
                names = ", ".join(q[0] for q in self.quants) or "none"
                raise ValueError(f"No {quant} weights for this profile (available: {names})")
            weights = Artifact(self.repo, self.revision, match[1], match[2], match[3])
        else:
            weights = Artifact(self.repo, self.revision, self.weights, *(self.weights_digest or ()))
        projector = Artifact(
            self.projector_repo or self.repo,
            self.projector_revision or self.revision,
            self.projector,
            *(self.projector_digest or ()),
        )
        return weights, projector


PROFILES = {
    "fast": Profile(
        "Qwen/Qwen3.5-0.8B",
        "unsloth/Qwen3.5-0.8B-GGUF",
        "6ab461498e2023f6e3c1baea90a8f0fe38ab64d0",
        "Qwen3.5-0.8B-Q4_K_M.gguf",
        weights_digest=(
            532517120,
            "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517",
        ),
        projector_digest=(
            204987232,
            "56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453",
        ),
    ),
    "balanced": Profile(
        "Qwen/Qwen3.5-4B",
        "unsloth/Qwen3.5-4B-GGUF",
        "e87f176479d0855a907a41277aca2f8ee7a09523",
        "Qwen3.5-4B-Q4_K_M.gguf",
        weights_digest=(
            2740937888,
            "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
        ),
        projector_digest=(
            672423616,
            "cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864",
        ),
    ),
    "quality": Profile(
        "Qwen/Qwen3.6-35B-A3B",
        "havenoammo/Qwen3.6-35B-A3B-MTP-GGUF",
        "a529a1734ce45a423a27a399d462791201d6995b",
        "Qwen3.6-35B-A3B-MTP-UD-Q4_K_XL.gguf",
        projector_repo="unsloth/Qwen3.6-35B-A3B-GGUF",
        projector_revision="a483e9e6cbd595906af30beda3187c2663a1118c",
        weights_digest=(
            23257919904,
            "ab94e2da12d2bdc22777ba1b7422bbf8d5d9d0bee1164ca7343a0cee3310038a",
        ),
        projector_digest=(
            899283680,
            "8971ee4f331ff0a4c609374f32984b3d4e6dc086c0aa35f1d637fad1829e887f",
        ),
    ),
    "max": Profile(
        "Qwen/Qwen3.8-27B",
        "unsloth/Qwen3.8-27B-GGUF",
        "4ca720788d1e01f1bff70c033e0d0028fd02e502",
        "Qwen3.8-27B-UD-Q4_K_XL.gguf",
        weights_digest=(
            17559178144,
            "3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e",
        ),
        projector_digest=(
            927607488,
            "cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e",
        ),
        quants=(
            (
                "Q8_0",
                "Qwen3.8-27B-Q8_0.gguf",
                29047086048,
                "a680f44a06920e5d689774823782006aa3acc8db95750323373b24139b67e348",
            ),
        ),
    ),
}
