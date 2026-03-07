# Third-Party Notices

This project bundles third-party software in Flatpak and AppImage builds:

## figma-agent-linux

- Project: `figma-agent-linux`
- Upstream: <https://github.com/neetly/figma-agent-linux>
- License: MIT
- Usage in this project:
  - Flatpak: bundled as `/app/bin/figma-agent`
  - AppImage: bundled under app resources and resolved at runtime
  - Purpose: local font helper compatibility for Figma

Redistribution of bundled binaries is subject to the upstream MIT license terms.
