#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/release-bundle.sh [--bump-patch] [--verify]

Builds a versioned Flatpak bundle in dist/ and generates a sha256 file.
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

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
cd "${ROOT_DIR}"

if [[ "${BUMP_PATCH}" == "1" ]]; then
  python - <<'PY'
import tomllib
from pathlib import Path

path = Path("pyproject.toml")
data = tomllib.loads(path.read_text("utf-8"))
major, minor, patch = map(int, data["project"]["version"].split("."))
old = f'{major}.{minor}.{patch}'
new = f'{major}.{minor}.{patch + 1}'
text = path.read_text("utf-8").replace(f'version = "{old}"', f'version = "{new}"', 1)
pkg = Path("figmux/__init__.py")
pkg_text = pkg.read_text("utf-8").replace(f'__version__ = "{old}"', f'__version__ = "{new}"', 1)
path.write_text(text, "utf-8")
pkg.write_text(pkg_text, "utf-8")
print(new)
PY
fi

VERSION="$(python - <<'PY'
import tomllib
from pathlib import Path
data = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))
print(data["project"]["version"])
PY
)"
ARTIFACT_NAME="figmux-${VERSION}-x86_64.flatpak"
ARTIFACT_PATH="${DIST_DIR}/${ARTIFACT_NAME}"
CHECKSUM_PATH="${ARTIFACT_PATH}.sha256"

echo "==> Building Flatpak bundle"
bash "${ROOT_DIR}/scripts/flatpak-build.sh"

mkdir -p "${DIST_DIR}"
cp -f "${ROOT_DIR}/com.figmux.app.flatpak" "${ARTIFACT_PATH}"
(
  cd "${DIST_DIR}"
  sha256sum "${ARTIFACT_NAME}" > "$(basename "${CHECKSUM_PATH}")"
)

if [[ "${VERIFY}" == "1" ]]; then
  flatpak uninstall --user -y com.figmux.app >/dev/null 2>&1 || true
  flatpak install --user -y "${ARTIFACT_PATH}"
  flatpak run --command=sh com.figmux.app -c 'test -x /app/bin/figma-agent'
fi

echo "==> Flatpak release ready"
echo "Bundle:   ${ARTIFACT_PATH}"
echo "SHA file: ${CHECKSUM_PATH}"
