#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/release-bundle.sh [--bump-patch] [--verify]

Builds a versioned shareable Flatpak bundle in dist/ and generates a sha256 file.

Options:
  --bump-patch  Increment package.json/package-lock.json patch version first.
  --verify   Reinstall locally and run smoke checks after bundle generation.
EOF
}

VERIFY=0
BUMP_PATCH=0
for arg in "$@"; do
  case "$arg" in
    --bump-patch)
      BUMP_PATCH=1
      ;;
    --verify)
      VERIFY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f package.json || ! -f scripts/flatpak-build.sh ]]; then
  echo "Run this script from the figmux repository root." >&2
  exit 1
fi

required_cmds=(node npm flatpak flatpak-builder sha256sum)
if [[ "${VERIFY}" == "1" ]]; then
  required_cmds+=(curl)
fi

for cmd in "${required_cmds[@]}"; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

if [[ "${BUMP_PATCH}" == "1" ]]; then
  echo "==> Bumping patch version"
  npm version patch --no-git-tag-version --force >/dev/null
fi

VERSION="$(node -p "require('./package.json').version")"
ARCH="x86_64"
DIST_DIR="${ROOT_DIR}/dist"
SOURCE_BUNDLE="${ROOT_DIR}/com.figmux.app.flatpak"
ARTIFACT_NAME="figmux-${VERSION}-${ARCH}.flatpak"
ARTIFACT_PATH="${DIST_DIR}/${ARTIFACT_NAME}"
CHECKSUM_PATH="${ARTIFACT_PATH}.sha256"

echo "==> Building Flatpak bundle"
npm run flatpak:build

if [[ ! -f "${SOURCE_BUNDLE}" ]]; then
  echo "Expected bundle not found: ${SOURCE_BUNDLE}" >&2
  exit 1
fi

mkdir -p "${DIST_DIR}"
cp -f "${SOURCE_BUNDLE}" "${ARTIFACT_PATH}"

(
  cd "${DIST_DIR}"
  sha256sum "${ARTIFACT_NAME}" > "$(basename "${CHECKSUM_PATH}")"
)

if [[ "${VERIFY}" == "1" ]]; then
  echo "==> Running local install and smoke checks"
  flatpak uninstall --user -y com.figmux.app >/dev/null 2>&1 || true
  flatpak install --user -y "${ARTIFACT_PATH}"

  flatpak run --command=sh com.figmux.app -c 'test -x /app/bin/figma-agent'

  TMP_LOG="$(mktemp)"
  cleanup() {
    if [[ -n "${AGENT_PID:-}" ]]; then
      kill "${AGENT_PID}" >/dev/null 2>&1 || true
      wait "${AGENT_PID}" >/dev/null 2>&1 || true
    fi
    rm -f "${TMP_LOG}"
  }
  trap cleanup EXIT

  flatpak run --command=figma-agent com.figmux.app >"${TMP_LOG}" 2>&1 &
  AGENT_PID=$!
  sleep 1
  curl -fsS http://127.0.0.1:44950/figma/version >/dev/null

  cleanup
  trap - EXIT
fi

CHECKSUM="$(cut -d' ' -f1 "${CHECKSUM_PATH}")"
echo "==> Release bundle ready"
echo "Bundle:   ${ARTIFACT_PATH}"
echo "Checksum: ${CHECKSUM}"
echo "SHA file: ${CHECKSUM_PATH}"
