#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .runtime
if [[ ! -x .runtime/venv/bin/python ]]; then
  python3.12 -m venv .runtime/venv
fi
.runtime/venv/bin/python -m pip install --upgrade pip uv
.runtime/venv/bin/python install_engine.py --python .runtime/venv/bin/python --report .runtime/engine.json
.runtime/venv/bin/python -m uv pip install --python .runtime/venv/bin/python -r requirements.txt
printf '0.10.0\n' > .runtime/cloud-ready
