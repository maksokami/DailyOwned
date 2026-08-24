#!/usr/bin/env bash
# Quick launcher — activates venv and runs the pipeline
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
python "$SCRIPT_DIR/src/pipeline.py" "$@"
