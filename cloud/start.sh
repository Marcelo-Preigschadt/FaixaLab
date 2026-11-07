#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export FAIXALAB_DATA_DIR="${FAIXALAB_DATA_DIR:-/workspaces/.faixalab-data}"
mkdir -p "$FAIXALAB_DATA_DIR"
if curl -fsS http://127.0.0.1:7860/api/health >/dev/null 2>&1; then
  printf 'FaixaLab já está aberto na porta privada 7860.\n'
  exit 0
fi
nohup bash .app/FaixaLab/cloud/start.sh > "$FAIXALAB_DATA_DIR/server.log" 2>&1 < /dev/null &
printf '%s\n' "$!" > "$FAIXALAB_DATA_DIR/server.pid"
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:7860/api/health >/dev/null 2>&1; then
    printf 'FaixaLab aberto. Na aba Ports, abra a porta privada 7860.\n'
    exit 0
  fi
  sleep 1
done
printf 'O servidor não respondeu. Consulte /workspaces/.faixalab-data/server.log.\n' >&2
exit 1
