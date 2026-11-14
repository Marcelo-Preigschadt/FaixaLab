#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

data="$HOME/Library/Application Support/FaixaLab/Importador"
mkdir -p "$data"
cp -R payload/. "$data/"
cd "$data"

if [[ ! -f .runtime/ready ]]; then
  mkdir -p .runtime
  if [[ ! -x .runtime/uv ]]; then
    case "$(uname -m)" in
      arm64) arch=aarch64 ;;
      x86_64) arch=x86_64 ;;
      *) echo 'Arquitetura incompatível.'; exit 1 ;;
    esac
    target="uv-$arch-apple-darwin"
    temp="$(mktemp -d)"
    trap 'rm -rf -- "$temp"' EXIT
    curl -fL --retry 2 --max-time 120 "https://github.com/astral-sh/uv/releases/download/0.11.28/$target.tar.gz" -o "$temp/uv.tar.gz"
    tar -xzf "$temp/uv.tar.gz" -C "$temp" "$target/uv"
    install -m 755 "$temp/$target/uv" .runtime/uv
  fi
  export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
  .runtime/uv python install 3.12
  [[ -x .venv/bin/python ]] || .runtime/uv venv --python 3.12 .venv
  .runtime/uv pip install --python .venv/bin/python --upgrade 'yt-dlp[default]>=2026.10.26' imageio-ffmpeg
  .venv/bin/python prepare_youtube.py
  printf '1\n' > .runtime/ready
fi
exec .venv/bin/python -m faixalab.local_import
