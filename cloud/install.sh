#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.12 cloud/bootstrap.py
bash .app/FaixaLab/cloud/setup.sh
