#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  echo "Error: .venv not found. Please create it with: python -m venv .venv"
  exit 1
fi

export PATH="$VENV_PATH/bin:$PATH"
export PYTHONPATH="$PROJECT_ROOT/backend"

echo "Using Python: $(which python)"
echo "PYTHONPATH set to: $PYTHONPATH"

python -B -m pytest backend/tests "$@"
