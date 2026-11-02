#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UV_BIN="${UV_BIN:-uv}"

if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  python3 -m pip install --user --upgrade uv
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js >=22.12 et npm sont requis pour construire le frontend." >&2
  exit 1
fi
cd "$PROJECT_ROOT/frontend"
if [ "${1:-}" = "--upgrade" ]; then
  npm update --no-fund
else
  npm ci --no-fund
fi
npm run build
cd "$PROJECT_ROOT"
if [ ! -d "$VENV_DIR" ]; then
  "$UV_BIN" venv "$VENV_DIR"
fi
if [ "${1:-}" = "--upgrade" ]; then
  "$UV_BIN" lock --upgrade
fi
UV_PROJECT_ENVIRONMENT="$VENV_DIR" "$UV_BIN" sync --locked --no-dev
printf 'Installation terminée. VENV_DIR=%s\n' "$VENV_DIR"
