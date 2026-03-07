#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/release-all.sh [--bump-patch] [--appimage-only] [--flatpak-only] [--verify-flatpak]

Build release artifacts in a deterministic sequence:
  - Flatpak bundle + checksum
  - AppImage bundle + checksum

Options:
  --bump-patch    Increment package patch version once before all releases.
  --appimage-only Build only AppImage artifacts.
  --flatpak-only  Build only Flatpak artifacts.
  --verify-flatpak Run Flatpak reinstall/smoke checks.
EOF
}

BUMP_PATCH=0
APPIMAGE_ONLY=0
FLATPAK_ONLY=0
VERIFY_FLATPAK=0

for arg in "$@"; do
  case "${arg}" in
    --bump-patch)
      BUMP_PATCH=1
      ;;
    --appimage-only)
      APPIMAGE_ONLY=1
      ;;
    --flatpak-only)
      FLATPAK_ONLY=1
      ;;
    --verify-flatpak)
      VERIFY_FLATPAK=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${APPIMAGE_ONLY}" == "1" && "${FLATPAK_ONLY}" == "1" ]]; then
  echo "Use only one of --appimage-only or --flatpak-only." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
cd "${ROOT_DIR}"

if [[ "${BUMP_PATCH}" == "1" ]]; then
  echo "==> Bumping patch version once for all release artifacts"
  npm version patch --no-git-tag-version --force >/dev/null
fi

echo "==> Cleaning old release artifacts"
mkdir -p "${DIST_DIR}"
rm -f "${DIST_DIR}"/figmux-*.flatpak "${DIST_DIR}"/figmux-*.flatpak.sha256
rm -f "${DIST_DIR}"/figmux-*.AppImage "${DIST_DIR}"/figmux-*.AppImage.sha256
rm -rf "${DIST_DIR}/linux-unpacked" "${DIST_DIR}/__appImage-x64" "${DIST_DIR}/builder-effective-config.yaml"
rm -f "${DIST_DIR}/latest-linux.yml"

if [[ "${APPIMAGE_ONLY}" != "1" ]]; then
  if [[ "${VERIFY_FLATPAK}" == "1" ]]; then
    npm run flatpak:release:verify
  else
    npm run flatpak:release
  fi
fi

if [[ "${FLATPAK_ONLY}" != "1" ]]; then
  npm run appimage:release
fi
