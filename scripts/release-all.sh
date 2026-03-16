#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/release-all.sh [--bump-patch] [--appimage-only] [--flatpak-only] [--verify-flatpak]
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
mkdir -p "${DIST_DIR}"
rm -f "${DIST_DIR}"/figmux-*.flatpak "${DIST_DIR}"/figmux-*.flatpak.sha256
rm -f "${DIST_DIR}"/figmux-*.AppImage "${DIST_DIR}"/figmux-*.AppImage.sha256

if [[ "${APPIMAGE_ONLY}" == "1" && "${BUMP_PATCH}" == "1" ]]; then
  python - <<'PY'
import tomllib
from pathlib import Path

path = Path("pyproject.toml")
data = tomllib.loads(path.read_text("utf-8"))
major, minor, patch = map(int, data["project"]["version"].split("."))
old = f'{major}.{minor}.{patch}'
new = f'{major}.{minor}.{patch + 1}'
path.write_text(path.read_text("utf-8").replace(f'version = "{old}"', f'version = "{new}"', 1), "utf-8")
pkg = Path("figmux/__init__.py")
pkg.write_text(pkg.read_text("utf-8").replace(f'__version__ = "{old}"', f'__version__ = "{new}"', 1), "utf-8")
print(new)
PY
  BUMP_PATCH=0
fi

if [[ "${APPIMAGE_ONLY}" != "1" ]]; then
  if [[ "${BUMP_PATCH}" == "1" ]]; then
    if [[ "${VERIFY_FLATPAK}" == "1" ]]; then
      bash "${ROOT_DIR}/scripts/release-bundle.sh" --bump-patch --verify
    else
      bash "${ROOT_DIR}/scripts/release-bundle.sh" --bump-patch
    fi
    BUMP_PATCH=0
  else
    if [[ "${VERIFY_FLATPAK}" == "1" ]]; then
      bash "${ROOT_DIR}/scripts/release-bundle.sh" --verify
    else
      bash "${ROOT_DIR}/scripts/release-bundle.sh"
    fi
  fi
fi

if [[ "${FLATPAK_ONLY}" != "1" ]]; then
  bash "${ROOT_DIR}/scripts/appimage-release.sh"
fi
