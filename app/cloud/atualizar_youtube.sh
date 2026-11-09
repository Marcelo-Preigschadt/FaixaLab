#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.runtime/venv/bin/python -m uv pip install --python .runtime/venv/bin/python --upgrade 'yt-dlp[default]>=2026.10.26'
.runtime/venv/bin/python prepare_youtube.py
printf 'Suporte ao YouTube atualizado e runtime validado. Reinicie o FaixaLab.\n'
