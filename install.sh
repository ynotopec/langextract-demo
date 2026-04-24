#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UV_BIN="${UV_BIN:-uv}"
UPGRADE="${1:-}"

ensure_uv() {
  if command -v "$UV_BIN" >/dev/null 2>&1; then
    return
  fi

  echo "uv not found. Installing with pip..."
  python3 -m pip install --user --upgrade uv
  export PATH="$HOME/.local/bin:$PATH"

  if ! command -v "$UV_BIN" >/dev/null 2>&1; then
    echo "Error: uv installation failed or is not in PATH." >&2
    exit 1
  fi
}

ensure_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment: $VENV_DIR"
    "$UV_BIN" venv "$VENV_DIR"
  fi
}

main() {
  ensure_uv
  ensure_venv

  cd "$PROJECT_ROOT"

  if [ "$UPGRADE" = "--upgrade" ]; then
    echo "Upgrading dependency lock..."
    "$UV_BIN" lock --upgrade
  fi

  echo "Syncing dependencies..."
  "$UV_BIN" sync

  echo "Done."
  echo "VENV_DIR=$VENV_DIR"
}

main "$@"
