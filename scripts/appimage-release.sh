#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT_DIR
DIST_DIR="${ROOT_DIR}/dist"
cd "${ROOT_DIR}"
VERSION="$(python - <<'PY'
import os
import tomllib
from pathlib import Path
root = Path(os.environ["ROOT_DIR"])
data = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
print(data["project"]["version"])
PY
)"
ARCH="x86_64"
SOURCE_PATH="${DIST_DIR}/figmux-${ARCH}.AppImage"
ARTIFACT_NAME="figmux-${VERSION}-${ARCH}.AppImage"
ARTIFACT_PATH="${DIST_DIR}/${ARTIFACT_NAME}"
CHECKSUM_PATH="${ARTIFACT_PATH}.sha256"

echo "==> Building AppImage artifact"
bash "${ROOT_DIR}/scripts/appimage-build.sh"

if [[ ! -f "${SOURCE_PATH}" ]]; then
  echo "Expected AppImage not found: ${SOURCE_PATH}" >&2
  exit 1
fi

cp -f "${SOURCE_PATH}" "${ARTIFACT_PATH}"
(
  cd "${DIST_DIR}"
  sha256sum "${ARTIFACT_NAME}" > "$(basename "${CHECKSUM_PATH}")"
)

echo "==> AppImage release ready"
echo "Bundle:   ${ARTIFACT_PATH}"
echo "SHA file: ${CHECKSUM_PATH}"
