#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m ensurepip --upgrade
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "${ROOT_DIR}"

if [[ ! -x "${ROOT_DIR}/resources/bin/figma-agent" ]]; then
  echo "figma-agent not installed at resources/bin/figma-agent"
  echo "Optional: bash scripts/install-figma-agent.sh"
fi

exec python "${ROOT_DIR}/main.py"
