# Changelog

## 0.3.3

- Fixed AppImage desktop integration so the dock icon resolves correctly once the app is installed into the app menu.
- Added native AppImage update download notifications with coarse progress milestones and a ready notification.
- Moved the in-app `Downloading Update` toast to the first real download-progress event so it shows more reliably during AppImage updates.

## 0.3.2

- Added a tab context menu with a reload action so an open Figma tab can be refreshed without leaving the tab strip.
- Limited tab activation to primary-button clicks so secondary-click actions can open the context menu cleanly.
- Adjusted the `+` tab button to create a fresh tab directly, instead of treating the current tab as the source for placement.

## 0.3.1

- Fixed Flatpak startup so the app window opens reliably even when `electron-updater` is not available in the bundle.
- Restored text-field editing focus after Alt-Tab by returning keyboard focus to the active Figma tab when Figmux regains focus.

## 0.3.0

- Improved Linux window integration with working edge snapping, restored Wayland pinch-to-zoom, and better custom title bar behavior.
- Added in-app update messaging for AppImage downloads and Flatpak release notices.
- Fixed Figma auth flows to stay in a dedicated popup again, with clearer popup loading feedback.
- Added tab restore and reordering, including `Ctrl+Shift+T`, drag-and-drop repositioning, and opening child tabs beside their source tab.
- Improved tab loading and close behavior with correct close animations, active-only close hit targets, and visible loading spinners.
- Fixed Figma-specific desktop integrations including fullscreen, image clipboard copy, and local font support via Windows browser spoofing plus `local-network-access`.
- Polished fullscreen layout, Flatpak foreground launch messaging, and other shell/titlebar UX details.

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
