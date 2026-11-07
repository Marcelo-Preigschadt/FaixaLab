#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .runtime/venv/bin/python ]]; then bash cloud/setup.sh; fi
export FAIXALAB_DATA_DIR="${FAIXALAB_DATA_DIR:-/workspaces/.faixalab-data}"
export PORT="${PORT:-7860}"
export FAIXALAB_CPU_THREADS="${FAIXALAB_CPU_THREADS:-2}"
export OMP_NUM_THREADS="$FAIXALAB_CPU_THREADS"
export MKL_NUM_THREADS="$FAIXALAB_CPU_THREADS"
export OPENBLAS_NUM_THREADS="$FAIXALAB_CPU_THREADS"
mkdir -p "$FAIXALAB_DATA_DIR"
exec .runtime/venv/bin/python server.py --port "$PORT"
