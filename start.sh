#!/usr/bin/env bash
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
(cd "$ROOT" && "$PY" -m uvicorn api.app:app --host 127.0.0.1 --port 8000) & API_PID=$!
(cd "$ROOT/web" && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev) & WEB_PID=$!
wait -n "$API_PID" "$WEB_PID"
