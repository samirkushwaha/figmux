#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERSION="$(node -p "require('${ROOT_DIR}/package.json').version")"
ARCH="x86_64"
ARTIFACT_NAME="figmux-${VERSION}-${ARCH}.AppImage"
ARTIFACT_PATH="${DIST_DIR}/${ARTIFACT_NAME}"
CHECKSUM_PATH="${ARTIFACT_PATH}.sha256"

required_cmds=(node npm sha256sum)
for cmd in "${required_cmds[@]}"; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

echo "==> Building AppImage artifact"
npm run appimage:build

if [[ ! -f "${ARTIFACT_PATH}" ]]; then
  echo "Expected AppImage not found: ${ARTIFACT_PATH}" >&2
  exit 1
fi

(
  cd "${DIST_DIR}"
  sha256sum "${ARTIFACT_NAME}" > "$(basename "${CHECKSUM_PATH}")"
)

CHECKSUM="$(cut -d' ' -f1 "${CHECKSUM_PATH}")"
echo "==> AppImage release ready"
echo "Bundle:   ${ARTIFACT_PATH}"
echo "Checksum: ${CHECKSUM}"
echo "SHA file: ${CHECKSUM_PATH}"
