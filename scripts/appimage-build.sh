#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT_DIR
cd "${ROOT_DIR}"
VENV_DIR="${ROOT_DIR}/.venv-appimage"
APPDIR="${ROOT_DIR}/dist/Figmux.AppDir"
PYI_DIST="${ROOT_DIR}/dist/figmux"
PYI_BUILD="${ROOT_DIR}/build"
TOOLS_DIR="${ROOT_DIR}/tools"
APPIMAGETOOL="${TOOLS_DIR}/appimagetool.AppImage"
CONTAINERFILE="${ROOT_DIR}/scripts/appimage-builder.Containerfile"
CONTAINER_IMAGE="${FIGMUX_APPIMAGE_CONTAINER_IMAGE:-figmux-appimage-builder:jammy}"
BUILD_MODE="${FIGMUX_APPIMAGE_BUILD_MODE:-container}"
PYTHON_VERSION="${FIGMUX_APPIMAGE_PYTHON_VERSION:-3.11}"
UV_CACHE_DIR="${ROOT_DIR}/.cache/uv-appimage"
UV_PYTHON_INSTALL_DIR="${ROOT_DIR}/.cache/uv-python"
FIGMA_AGENT_URL="https://github.com/neetly/figma-agent-linux/releases/download/0.4.3/figma-agent-x86_64-unknown-linux-gnu"
FIGMA_AGENT_SHA256="85661938e54ad5f6c4af7101d7a7375b1f0f9f132c0c517530b39eea8388656c"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
VERSION="$(awk -F '"' '/^version = / { print $2; exit }' "${ROOT_DIR}/pyproject.toml")"

build_in_container() {
  if ! command -v podman >/dev/null 2>&1; then
    echo "Podman is required for the default AppImage build path." >&2
    echo "Set FIGMUX_APPIMAGE_BUILD_MODE=host to bypass the containerized build." >&2
    exit 1
  fi

  echo "==> Building AppImage inside Podman (${CONTAINER_IMAGE})"
  podman build -t "${CONTAINER_IMAGE}" -f "${CONTAINERFILE}" "${ROOT_DIR}"
  podman run --rm \
    --userns=keep-id \
    --user "$(id -u):$(id -g)" \
    --security-opt label=disable \
    -e FIGMUX_APPIMAGE_BUILD_MODE=host \
    -e FIGMUX_APPIMAGE_PYTHON_VERSION="${PYTHON_VERSION}" \
    -e HOME=/tmp/figmux-appimage-home \
    -e ROOT_DIR="${ROOT_DIR}" \
    -v "${ROOT_DIR}:${ROOT_DIR}" \
    -w "${ROOT_DIR}" \
    "${CONTAINER_IMAGE}" \
    bash scripts/appimage-build.sh
}

ensure_python() {
  mkdir -p "${UV_CACHE_DIR}" "${UV_PYTHON_INSTALL_DIR}"
  export UV_CACHE_DIR
  export UV_PYTHON_INSTALL_DIR

  if command -v uv >/dev/null 2>&1; then
    uv python install "${PYTHON_VERSION}"
    uv venv --seed --python "${PYTHON_VERSION}" "${VENV_DIR}"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv "${VENV_DIR}"
    return
  fi

  echo "Neither uv nor python3 is available to create ${VENV_DIR}." >&2
  exit 1
}

if [[ "${BUILD_MODE}" != "host" ]]; then
  build_in_container
  exit 0
fi

if [[ ! -x "${APPIMAGETOOL}" ]]; then
  mkdir -p "${TOOLS_DIR}"
  curl -fsSL "${APPIMAGETOOL_URL}" -o "${APPIMAGETOOL}"
  chmod +x "${APPIMAGETOOL}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  ensure_python
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
pyinstaller --noconfirm --clean "${ROOT_DIR}/figmux.spec"
python "${ROOT_DIR}/scripts/verify-appimage-tiff.py" "${PYI_DIST}"

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

APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "${APPIMAGETOOL}" "${APPDIR}" "${ROOT_DIR}/dist/figmux-x86_64.AppImage"
