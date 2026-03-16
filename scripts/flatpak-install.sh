#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="${ROOT_DIR}/com.figmux.app.flatpak"

if [[ ! -f "${BUNDLE}" ]]; then
  echo "Bundle not found: ${BUNDLE}" >&2
  echo "Run bash scripts/flatpak-build.sh first." >&2
  exit 1
fi

flatpak uninstall --user -y com.figmux.app >/dev/null 2>&1 || true
flatpak install --user -y "${BUNDLE}"
