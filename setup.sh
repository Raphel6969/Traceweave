#!/usr/bin/env bash
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt" -e "$ROOT"
(cd "$ROOT/web" && npm install)
echo "TraceWeave is ready. Run ./start.sh"
