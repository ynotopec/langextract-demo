#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="$(basename "$(pwd)")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi

  echo "uv not found. Installing with pip..."
  python3 -m pip install --user --upgrade uv

  if [ -d "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  fi

  if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv installation failed or not in PATH." >&2
    exit 1
  fi
}

ensure_uv

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at: $VENV_DIR"
  uv venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "Upgrading lock file and syncing environment..."
uv lock --upgrade
uv sync

echo "Done. Updated dependencies are locked and installed."
