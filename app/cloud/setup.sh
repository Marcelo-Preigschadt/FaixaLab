#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .runtime
if [[ ! -x .runtime/venv/bin/python ]]; then
  python3.12 -m venv .runtime/venv
fi
.runtime/venv/bin/python -m pip install --upgrade pip uv
.runtime/venv/bin/python -m uv pip install --python .runtime/venv/bin/python torch==2.5.1+cpu torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
.runtime/venv/bin/python -m uv pip install --python .runtime/venv/bin/python -r requirements.txt
printf '0.8.0\n' > .runtime/cloud-ready
