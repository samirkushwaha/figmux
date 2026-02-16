#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/.flatpak-builder"
REPO_DIR="${ROOT_DIR}/.flatpak-repo"
STATE_DIR="${ROOT_DIR}/.flatpak-state"
MANIFEST="${ROOT_DIR}/flatpak/com.figmux.app.yml"

rm -rf "${BUILD_DIR}"

(
  cd /tmp
  flatpak-builder --state-dir="${STATE_DIR}" --user --repo="${REPO_DIR}" "${BUILD_DIR}" "${MANIFEST}"
)
flatpak build-bundle "${REPO_DIR}" "${ROOT_DIR}/com.figmux.app.flatpak" com.figmux.app master --arch=x86_64
