#!/usr/bin/env bash
# Build llama-server with OpenJev's patches into .llamacpp/ (ignored by Git).
#
# The patches add per-request checkpoint controls to llama-server. With them, requests
# that repeat a state on hybrid Qwen models read only their question; see site/models.md.
# Stock llama.cpp still works with OpenJev, only slower on those requests.
#
#   scripts/build-llama.sh
#   uv run openjev serve --profile max   # uses this build automatically
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=6f41ac59e0a49a00483a316a22ada6b04edd2950  # llama.cpp master, 2026-09-21
DIR="$ROOT/.llamacpp/llama.cpp"

if [ ! -d "$DIR/.git" ]; then
  git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$DIR"
fi
git -C "$DIR" fetch --quiet origin "$BASE"
git -C "$DIR" checkout --quiet --force -B openjev "$BASE"
GIT_COMMITTER_NAME=openjev GIT_COMMITTER_EMAIL=openjev@localhost \
  git -C "$DIR" am --quiet "$ROOT"/patches/llama.cpp/*.patch

cmake -S "$DIR" -B "$DIR/build" -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_CURL=OFF > /dev/null
cmake --build "$DIR/build" --config Release -j --target llama-server
echo "$DIR/build/bin/llama-server"
