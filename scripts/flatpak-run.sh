#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="${ROOT_DIR}/.flatpak-repo"

flatpak --user remote-add --if-not-exists --no-gpg-verify figmux-local "${REPO_DIR}"
flatpak --user install -y --reinstall figmux-local com.figmux.app
echo "Launching Figmux in the foreground..."
exec flatpak run com.figmux.app
