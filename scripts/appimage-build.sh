#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT_DIR
VENV_DIR="${ROOT_DIR}/.venv"
APPDIR="${ROOT_DIR}/dist/Figmux.AppDir"
PYI_DIST="${ROOT_DIR}/dist/figmux"
PYI_BUILD="${ROOT_DIR}/build"
TOOLS_DIR="${ROOT_DIR}/tools"
APPIMAGETOOL="${TOOLS_DIR}/appimagetool.AppImage"
FIGMA_AGENT_URL="https://github.com/neetly/figma-agent-linux/releases/download/0.4.3/figma-agent-x86_64-unknown-linux-gnu"
FIGMA_AGENT_SHA256="85661938e54ad5f6c4af7101d7a7375b1f0f9f132c0c517530b39eea8388656c"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
VERSION="$(python3 - <<'PY'
import os
import tomllib
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
data = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
print(data["project"]["version"])
PY
)"

if [[ ! -x "${APPIMAGETOOL}" ]]; then
  mkdir -p "${TOOLS_DIR}"
  curl -fsSL "${APPIMAGETOOL_URL}" -o "${APPIMAGETOOL}"
  chmod +x "${APPIMAGETOOL}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m ensurepip --upgrade
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "${ROOT_DIR}[build]"

mkdir -p "${ROOT_DIR}/resources/bin"
TMP_AGENT="$(mktemp)"
trap 'rm -f "${TMP_AGENT}"' EXIT
curl -fsSL "${FIGMA_AGENT_URL}" -o "${TMP_AGENT}"
echo "${FIGMA_AGENT_SHA256}  ${TMP_AGENT}" | sha256sum -c -
install -Dm755 "${TMP_AGENT}" "${ROOT_DIR}/resources/bin/figma-agent"

rm -rf "${APPDIR}" "${PYI_DIST}" "${PYI_BUILD}"
pyinstaller \
  --noconfirm \
  --clean \
  --name figmux \
  --specpath "${PYI_BUILD}" \
  --icon "${ROOT_DIR}/assets/com.figmux.app.png" \
  --collect-submodules PyQt6.QtWebEngineCore \
  --collect-submodules PyQt6.QtWebEngineWidgets \
  --collect-submodules PyQt6.QtWebEngineQuick \
  --add-data "${ROOT_DIR}/assets:assets" \
  --add-data "${ROOT_DIR}/resources:resources" \
  "${ROOT_DIR}/main.py"

mkdir -p "${APPDIR}/usr/lib/figmux" "${APPDIR}/usr/bin" "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/scalable/apps" "${APPDIR}/usr/share/icons/hicolor/512x512/apps" "${APPDIR}/usr/share/metainfo"
cp -r "${PYI_DIST}/." "${APPDIR}/usr/lib/figmux/"
cp "${ROOT_DIR}/flatpak/com.figmux.app.desktop" "${APPDIR}/usr/share/applications/com.figmux.app.desktop"
cat <<EOF >> "${APPDIR}/usr/share/applications/com.figmux.app.desktop"
X-AppImage-Name=Figmux
X-AppImage-Version=${VERSION}
X-AppImage-Arch=x86_64
EOF
cp "${ROOT_DIR}/flatpak/com.figmux.app.metainfo.xml" "${APPDIR}/usr/share/metainfo/com.figmux.app.metainfo.xml"
cp "${ROOT_DIR}/flatpak/com.figmux.app.metainfo.xml" "${APPDIR}/usr/share/metainfo/com.figmux.app.appdata.xml"
cp "${ROOT_DIR}/assets/com.figmux.app.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/com.figmux.app.svg"
cp "${ROOT_DIR}/assets/com.figmux.app.png" "${APPDIR}/usr/share/icons/hicolor/512x512/apps/com.figmux.app.png"
install -Dm755 /dev/stdin "${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${HERE}/usr/lib/figmux/figmux" "$@"
EOF
ln -sf usr/share/icons/hicolor/scalable/apps/com.figmux.app.svg "${APPDIR}/com.figmux.app.svg"
ln -sf usr/share/applications/com.figmux.app.desktop "${APPDIR}/com.figmux.app.desktop"

ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "${ROOT_DIR}/dist/figmux-x86_64.AppImage"
