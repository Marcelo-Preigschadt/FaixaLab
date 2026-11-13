#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if ! command -v pkg >/dev/null || [[ -z "${TERMUX_VERSION:-}" ]]; then
  echo 'Abra este instalador no Termux para Android.'
  exit 1
fi
if [[ ! -f .runtime/ready || "${1:-}" == --atualizar ]]; then
  pkg install -y python python-pip ffmpeg nodejs
  python -m venv .venv
  # Termux supplies FFmpeg and Node. Keep pip dependencies pure Python.
  .venv/bin/python -m pip install --upgrade 'yt-dlp>=2026.10.26' yt-dlp-ejs
  .venv/bin/python prepare_youtube.py --check
  mkdir -p .runtime
  printf '1\n' > .runtime/ready
fi
exec .venv/bin/python -m faixalab.local_import
