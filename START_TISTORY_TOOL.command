#!/bin/zsh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source ".venv/bin/activate"

python -m pip install -r requirements.txt >/dev/null 2>&1 || true

PORT=8505

# Try to free the port if a previous instance exists (best-effort).
pkill -f "streamlit run app.py" >/dev/null 2>&1 || true

open "http://127.0.0.1:${PORT}"
streamlit run app.py --server.port "${PORT}"

