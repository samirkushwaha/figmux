# Changelog

## 0.1.2

- Added AppImage release artifacts alongside Flatpak artifacts.
- Bundled `figma-agent` support now works across Flatpak and AppImage packaging.
- Cleaned release scripts so `dist/` keeps only final user-facing artifacts and checksums.
- Simplified runtime helper path resolution and shutdown cleanup.
- Kept the login/captcha mitigation that avoids forcing Windows UA on auth pages.
