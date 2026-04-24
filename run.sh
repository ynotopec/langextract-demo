#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
IP="${1:-127.0.0.1}"
PORT="${2:-8501}"

# shellcheck source=/dev/null
source "$PROJECT_ROOT/install.sh"

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

cd "$PROJECT_ROOT"

echo "Starting Streamlit on $IP:$PORT"
exec streamlit run app.py --server.address "$IP" --server.port "$PORT"
