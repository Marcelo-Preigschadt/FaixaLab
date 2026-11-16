#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if [[ ! -f .runtime/ready || "${1:-}" == --atualizar || "${2:-}" == --atualizar ]]; then
  if ! command -v python3 >/dev/null || ! python3 -m venv .venv; then
    echo 'Não foi possível preparar o ambiente Python do importador.' >&2
    exit 1
  fi
  .venv/bin/python -m pip install --upgrade 'yt-dlp[default]>=2026.10.26'
  if ! command -v ffmpeg >/dev/null; then
    .venv/bin/python -m pip install imageio-ffmpeg
  fi
  .venv/bin/python prepare_youtube.py
  mkdir -p .runtime
  printf '1\n' > .runtime/ready
fi
if [[ "${1:-}" == --prepare ]]; then
  exit 0
fi
exec .venv/bin/python -m faixalab.local_import
