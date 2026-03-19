from __future__ import annotations

from pathlib import Path

APP_ID = "com.figmux.app"
APP_NAME = "Figmux"
ORGANIZATION_NAME = "figmux"
ORGANIZATION_DOMAIN = "figmux.app"
AUTH_POPUP_TITLE = f"{APP_NAME} Sign In"
GITHUB_REPO = "samirkushwaha/figmux"

FIGMA_HOME = "https://www.figma.com"
FIGMA_RECENTS = "https://www.figma.com/files/recent"
FIGMA_AGENT_VERSION_URL = "http://127.0.0.1:44950/figma/version"
SESSION_STATE_FILE = "tabs-state.json"
WINDOW_MIN_WIDTH = 1080
WINDOW_MIN_HEIGHT = 720
TITLEBAR_HEIGHT = 40
CLOSED_TABS_LIMIT = 20
WINDOWS_PLATFORM = "Win32"
WINDOWS_CHROMIUM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

FIGMA_AGENT_DOWNLOAD_URL = (
    "https://github.com/neetly/figma-agent-linux/releases/download/0.4.3/"
    "figma-agent-x86_64-unknown-linux-gnu"
)
FIGMA_AGENT_SHA256 = "85661938e54ad5f6c4af7101d7a7375b1f0f9f132c0c517530b39eea8388656c"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
RESOURCES_DIR = PROJECT_ROOT / "resources"
APPIMAGE_FIGMA_AGENT_RELATIVE_PATH = Path("resources") / "bin" / "figma-agent"
FLATPAK_FIGMA_AGENT_PATH = Path("/app/bin/figma-agent")
