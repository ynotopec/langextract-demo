#!/usr/bin/env bash
# Subshell preserves the calling shell when used with `source run.sh`.
(
  set -euo pipefail
  PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  VENV_DIR="${VENV_DIR:-$HOME/venv/$(basename "$PROJECT_ROOT")}"
  IP="${1:-127.0.0.1}"
  PORT="${2:-8501}"
  if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
    bash "$PROJECT_ROOT/install.sh"
  fi
  cd "$PROJECT_ROOT"
  # python-dotenv loads .env literally; secrets containing $ are not shell code.
  exec "$VENV_DIR/bin/python" -m uvicorn app:app --host "$IP" --port "$PORT" --no-access-log
)
