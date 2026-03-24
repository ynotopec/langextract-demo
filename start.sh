#!/usr/bin/env bash
set -euo pipefail

IP="${1:-127.0.0.1}"
PORT="${2:-8501}"
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

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "Syncing dependencies with uv..."
uv sync

echo "Starting Streamlit on $IP:$PORT"
exec streamlit run app.py --server.address "$IP" --server.port "$PORT"
