#!/usr/bin/env bash
set -euo pipefail

exec flatpak run com.figmux.app "$@"
