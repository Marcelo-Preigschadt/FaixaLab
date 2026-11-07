#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.12 cloud/bootstrap.py
python3.12 cloud/link_models.py
bash app/cloud/setup.sh
