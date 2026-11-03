#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UV_BIN="${UV_BIN:-uv}"

# Reuse a suitable system runtime, otherwise bootstrap Node 24 via npx.
node_supported() {
  command -v node >/dev/null 2>&1 &&
    node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit((major === 24 && minor >= 15) || major >= 26 ? 0 : 1)'
}
if ! node_supported; then
  if [ "${LANGEXTRACT_NODE_BOOTSTRAPPED:-}" = "1" ]; then
    echo "Le Node fourni par npx reste incompatible (Node 24 >=24.15.0 ou >=26 requis)." >&2
    exit 1
  fi
  if ! command -v npx >/dev/null 2>&1; then
    echo "Node incompatible et npx introuvable : installer Node 24 >=24.15.0 ou npm/npx pour le démarrage automatique." >&2
    exit 1
  fi
  echo "Node absent ou incompatible : utilisation automatique de Node 24 via npx."
  export LANGEXTRACT_NODE_BOOTSTRAPPED=1 VENV_DIR UV_BIN
  # Separate arguments preserve paths with spaces, --upgrade and caller options.
  exec npx --yes --package=node@24 -- bash "$PROJECT_ROOT/install.sh" "$@"
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm est requis pour construire le frontend." >&2
  exit 1
fi
if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  python3 -m pip install --user --upgrade uv
  export PATH="$HOME/.local/bin:$PATH"
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
