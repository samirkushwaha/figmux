# Changelog

## 0.2.0

- Upgraded Electron to `38.8.4`, which restores working touchpad pinch-to-zoom on Wayland.
- Kept Linux edge snapping working while returning to a custom title bar via `titleBarOverlay`.
- Fixed inactive-tab close hit targets so only the visible close button closes a tab.
- Fixed keyboard tab-close animations so `Ctrl+W` collapses the correct tab.
- Polished the tab strip with better focus handling, separator rendering, and fullscreen behavior.
- Added clipboard and fullscreen permission handling so image copy and Figma fullscreen work correctly.
- Hide the custom tab bar while a Figma design is in fullscreen.
- Improved Flatpak foreground launch feedback with an explicit launch message.
- Updated the packaged app description to `Dedicated Linux desktop wrapper for Figma`.

## 0.1.2

- Added AppImage release artifacts alongside Flatpak artifacts.
- Bundled `figma-agent` support now works across Flatpak and AppImage packaging.
- Cleaned release scripts so `dist/` keeps only final user-facing artifacts and checksums.
- Simplified runtime helper path resolution and shutdown cleanup.
- Kept the login/captcha mitigation that avoids forcing Windows UA on auth pages.
- Added AppImage in-app update support via `electron-updater` and GitHub Releases metadata (`latest-linux.yml`).
