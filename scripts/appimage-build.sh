#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
FIGMA_AGENT_URL="https://github.com/neetly/figma-agent-linux/releases/download/0.4.3/figma-agent-x86_64-unknown-linux-gnu"
FIGMA_AGENT_SHA256="85661938e54ad5f6c4af7101d7a7375b1f0f9f132c0c517530b39eea8388656c"
RESOURCES_BIN_DIR="${ROOT_DIR}/resources/bin"
RESOURCES_FIGMA_AGENT="${RESOURCES_BIN_DIR}/figma-agent"

required_cmds=(npm curl sha256sum npx)
for cmd in "${required_cmds[@]}"; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

mkdir -p "${RESOURCES_BIN_DIR}"

tmp_agent="$(mktemp)"
cleanup() {
  rm -f "${tmp_agent}"
}
trap cleanup EXIT

echo "==> Downloading bundled figma-agent for AppImage"
curl -fsSL "${FIGMA_AGENT_URL}" -o "${tmp_agent}"
echo "${FIGMA_AGENT_SHA256}  ${tmp_agent}" | sha256sum -c -
install -Dm755 "${tmp_agent}" "${RESOURCES_FIGMA_AGENT}"

echo "==> Cleaning transient AppImage build outputs"
rm -rf "${DIST_DIR}/linux-unpacked" "${DIST_DIR}/__appImage-x64" "${DIST_DIR}/builder-effective-config.yaml"

echo "==> Building AppImage"
npx electron-builder --linux AppImage --x64 --publish never

echo "==> Removing transient AppImage build outputs"
rm -rf "${DIST_DIR}/linux-unpacked" "${DIST_DIR}/__appImage-x64" "${DIST_DIR}/builder-effective-config.yaml"
