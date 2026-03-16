#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${ROOT_DIR}/resources/bin"
DEST_PATH="${DEST_DIR}/figma-agent"
FIGMA_AGENT_URL="https://github.com/neetly/figma-agent-linux/releases/download/0.4.3/figma-agent-x86_64-unknown-linux-gnu"
FIGMA_AGENT_SHA256="85661938e54ad5f6c4af7101d7a7375b1f0f9f132c0c517530b39eea8388656c"

for cmd in curl sha256sum install mktemp; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

mkdir -p "${DEST_DIR}"
TMP_AGENT="$(mktemp)"
trap 'rm -f "${TMP_AGENT}"' EXIT

echo "==> Downloading figma-agent-linux"
curl -fsSL "${FIGMA_AGENT_URL}" -o "${TMP_AGENT}"
echo "${FIGMA_AGENT_SHA256}  ${TMP_AGENT}" | sha256sum -c -
install -Dm755 "${TMP_AGENT}" "${DEST_PATH}"
echo "Installed ${DEST_PATH}"
