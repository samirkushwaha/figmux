# Figmux

Figmux is a Linux desktop wrapper for [Figma](https://www.figma.com) built with Electron.

## Features

- Opens `https://www.figma.com` in a dedicated desktop window.
- Uses a persistent Electron partition: `persist:figmux`.
- Includes a custom titlebar tab strip with `+` button for multiple Figma tabs.
- Restores open tabs on restart.
- `+` always opens `https://www.figma.com/files/recent`.
- Opens non-auth `window.open` requests from Figma as new in-app tabs.
- Keeps OAuth sign-in popups in-app for callback compatibility.
- Routes non-Figma external links to the system browser.
- Reflows active content correctly on resize, maximize, unmaximize, and fullscreen transitions.
- Uses overlay-native window controls and adapts tab colors to light/dark system theme.
- Ships with Flatpak metadata for app ID `com.figmux.app`.
- Flatpak and AppImage builds bundle `figma-agent-linux` (https://github.com/neetly/figma-agent-linux) and auto-start it for local font support in Figma.
All thanks to Neetly for creating this super useful figma agent.

## Prerequisites

### Local Electron development

- Node.js 20+
- npm

### Flatpak build and run

- `flatpak`
- `flatpak-builder`
- Runtimes:
  - `org.freedesktop.Platform//24.08`
  - `org.freedesktop.Sdk//24.08`
  - `org.electronjs.Electron2.BaseApp//24.08`

Install runtimes if needed:

```bash
flatpak install flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08 org.electronjs.Electron2.BaseApp//24.08
```

## Local development

Install dependencies:

```bash
npm install
```

Run app locally:

```bash
npm run dev
```

Run syntax checks:

```bash
npm run lint
```

## Flatpak build and run

Build package:

```bash
npm run flatpak:build
```

Install locally and run:

```bash
npm run flatpak:run
```

## AppImage build and run

Build AppImage:

```bash
npm run appimage:build
```

Run AppImage:

```bash
chmod +x dist/figmux-<version>-x86_64.AppImage
./dist/figmux-<version>-x86_64.AppImage
```

## Local Flatpak export

This flow creates a local `.flatpak` bundle and installs it so the OS app launcher can open Figmux.

```bash
npm install
npm run flatpak:build
flatpak uninstall --user -y com.figmux.app
flatpak install --user ./com.figmux.app.flatpak
flatpak run com.figmux.app
```

Notes:
- `npm run dev` is for local Electron development only and does not create launcher integration.
- Launcher integration comes from the Flatpak install (`com.figmux.app` desktop entry).
- If you use a local repo remote (`figmux-local`), installing from the bundle path ensures you run the exact build you just created.
- Flatpak builds are preconfigured for Figma local fonts (bundled `figma-agent` on `127.0.0.1:44950`).
- Local Electron development (`npm run dev`) does not bundle `figma-agent`; use an external/local listener if you need fonts.

## Shareable release bundles

Build versioned artifacts for both Flatpak and AppImage (single patch bump):

```bash
npm run release:all
```

This command auto-increments the patch version (`x.y.z` -> `x.y.(z+1)`) once, then builds both package formats.

Build only Flatpak artifact (no version bump):

```bash
npm run flatpak:release
```

Build only AppImage artifact (no version bump):

```bash
npm run appimage:release
```

Combined entrypoint variants (single patch bump):

```bash
npm run release:all:flatpak
npm run release:all:appimage
```

This writes:
- `dist/figmux-<version>-x86_64.flatpak`
- `dist/figmux-<version>-x86_64.flatpak.sha256`
- `dist/figmux-<version>-x86_64.AppImage`
- `dist/figmux-<version>-x86_64.AppImage.sha256`
- `dist/latest-linux.yml`

Verify checksum:

```bash
cd dist
sha256sum -c figmux-<version>-x86_64.flatpak.sha256
sha256sum -c figmux-<version>-x86_64.AppImage.sha256
```

For AppImage auto-updates, `latest-linux.yml` must be uploaded to the matching GitHub Release alongside the `.AppImage`.

Optional local install + smoke verification:

```bash
npm run release:all:verify
```

`release:all:verify` includes Flatpak reinstall/smoke checks:
- local install from the versioned artifact succeeds
- `/app/bin/figma-agent` exists in the sandbox
- `http://127.0.0.1:44950/figma/version` responds while helper process runs

## Legal / Attribution

- Figmux is an unofficial wrapper and is not affiliated with, endorsed by, or sponsored by Figma.
- "Figma" and related marks are trademarks of their respective owners.
- Flatpak and AppImage builds bundle `figma-agent-linux` (MIT): <https://github.com/neetly/figma-agent-linux>
- See [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) for bundled dependency notices.

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for release notes.

## Updates

- AppImage builds use in-app update checks via GitHub Releases.
- On startup, packaged AppImage builds check for a newer release and prompt before downloading.
- AppImage GitHub releases must include:
  - `figmux-<version>-x86_64.AppImage`
  - `figmux-<version>-x86_64.AppImage.sha256`
  - `latest-linux.yml`
- Flatpak builds do not use the in-app updater. Update Flatpak manually:

```bash
flatpak install --user --reinstall ./dist/figmux-<version>-x86_64.flatpak
```

- GitHub Releases remains the canonical public release page for both AppImage and Flatpak downloads.

## Publishing checklist

Run before publishing the repo or creating a release:

```bash
rg -n "(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-|BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY|api[_-]?key|secret|token|password|passwd)" -S --hidden --glob '!node_modules/**' --glob '!.git/**'
npm run lint
npm run release:all
```

After `npm run release:all`, verify:
- `dist/figmux-<version>-x86_64.flatpak`
- `dist/figmux-<version>-x86_64.flatpak.sha256`
- `dist/figmux-<version>-x86_64.AppImage`
- `dist/figmux-<version>-x86_64.AppImage.sha256`
- `dist/latest-linux.yml`
- `package.json` and `package-lock.json` were bumped to the new patch version

GitHub AppImage updater publishing checklist:
- push the release commit and tag
- create a GitHub Release for the matching tag
- upload `.AppImage`, `.AppImage.sha256`, and `latest-linux.yml`
- upload Flatpak artifacts and checksum

## Authentication behavior

- OAuth login flows (including Google) open in an in-app popup window so Figma can complete auth callbacks.
- Non-auth popup URLs from Figma open as new in-app tabs.
- Figma pages under `figma.com` continue to navigate inside the main app window.
- Session data still persists in the Electron partition `persist:figmux`.

## Tabs and shortcuts

- `+` button: open a new Figma tab.
- New tabs always start at `https://www.figma.com/files/recent`.
- `Ctrl+T`: open new tab.
- `Ctrl+W`: close active tab.
- `Ctrl+Tab`: next tab.
- `Ctrl+Shift+Tab`: previous tab.
- Closing the last tab immediately creates a fresh Figma tab.
- Open tabs are restored on app restart.

## Session persistence verification

1. Start Figmux and sign into Figma.
2. Close the app fully.
3. Re-open Figmux.
4. Confirm the session remains authenticated.

If sessions are lost, verify `src/main.js` still uses `partition: "persist:figmux"` and the app ID remains `com.figmux.app`.

## Troubleshooting

- Messages like `GetVSyncParametersIfAvailable() failed` are usually Chromium graphics timing warnings and can be ignored unless you see visible rendering glitches, freezes, or crashes.
- If local fonts do not appear in Figma:
  - Keep Figmux running and verify the agent endpoint: `curl -fsS http://127.0.0.1:44950/figma/version`
  - Start Figmux from terminal and watch startup logs for agent warnings: `flatpak run com.figmux.app` or `./dist/figmux-<version>-x86_64.AppImage`
  - Look for `[figmux]` messages such as bundled agent missing/unreachable.
- AppImage does not require Flatpak runtimes and installs no system package by default.
- If clicking the OS launcher does nothing:
  - Verify installation: `flatpak list --app | grep com.figmux.app`
  - Run directly to inspect errors: `flatpak run com.figmux.app`
  - Verify GPU device exposure in sandbox: `flatpak run --command=sh com.figmux.app -c 'ls -l /dev/dri || true'`
  - Wayland/X11 variables inside sandbox: `flatpak run --command=sh com.figmux.app -c 'echo DISPLAY=$DISPLAY WAYLAND_DISPLAY=$WAYLAND_DISPLAY XDG_SESSION_TYPE=$XDG_SESSION_TYPE'`
  - `Failed to connect to socket /run/dbus/system_bus_socket` can appear and is usually not the primary blocker.
  - GPU/EGL/ozone crashes are actionable and usually indicate missing GPU access or driver/runtime mismatch.
  - If icon or launcher metadata appears stale, unpin Figmux from your dock/taskbar, launch it again from app grid, then re-pin.
