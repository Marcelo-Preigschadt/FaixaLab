#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../app"

: "${FAIXALAB_API_KEY:?Configure a chave interna do servidor}"
: "${FAIXALAB_PAGES_KEY:?Configure a chave de assinatura das sessões}"
: "${FAIXALAB_PAGES_URL:?Configure a URL do GitHub Pages}"
: "${FAIXALAB_GOOGLE_CLIENT_ID:?Configure o cliente Web do Google}"

export FAIXALAB_REMOTE=1
export PORT=7860
python server.py --host 127.0.0.1 --port "$PORT" &
processor=$!
gateway=''
cleanup() {
  kill "$processor" ${gateway:+"$gateway"} 2>/dev/null || true
  wait "$processor" ${gateway:+"$gateway"} 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

env -u FAIXALAB_YOUTUBE_COOKIES -u FAIXALAB_AUDIO_SOURCE_KEY python -m faixalab.pages_gateway &
gateway=$!
wait -n "$processor" "$gateway"
exit 1
