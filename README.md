# Figmux

Figmux is a Linux desktop wrapper for [Figma](https://www.figma.com) built with Electron and Flatpak.

## Features

- Opens `https://www.figma.com` in a dedicated desktop window.
- Uses a persistent Electron partition: `persist:figmux`.
- Allows Figma/Google OAuth sign-in popups in-app for callback compatibility.
- Routes non-auth popups and non-Figma links to the system browser.
- Ships with Flatpak metadata for app ID `com.figmux.app`.

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

## Authentication behavior

- OAuth login flows (including Google) open in an in-app popup window so Figma can complete auth callbacks.
- Non-auth popup URLs are denied in-app and opened in your default system browser.
- Figma pages under `figma.com` continue to navigate inside the main app window.
- Session data still persists in the Electron partition `persist:figmux`.

## Session persistence verification

1. Start Figmux and sign into Figma.
2. Close the app fully.
3. Re-open Figmux.
4. Confirm the session remains authenticated.

If sessions are lost, verify `src/main.js` still uses `partition: "persist:figmux"` and the app ID remains `com.figmux.app`.

## Troubleshooting

- Messages like `GetVSyncParametersIfAvailable() failed` are usually Chromium graphics timing warnings and can be ignored unless you see visible rendering glitches, freezes, or crashes.
