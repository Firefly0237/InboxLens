#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  python3 -m venv "$PROJECT_ROOT/.venv"
fi

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e "$PROJECT_ROOT[html]"
"$PYTHON" -m inbox_lens console
