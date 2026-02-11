# Figmux

Figmux is a Linux desktop wrapper for [Figma](https://www.figma.com) built with Electron and Flatpak.

## Features

- Opens `https://www.figma.com` in a dedicated desktop window.
- Uses a persistent Electron partition: `persist:figmux`.
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

## Session persistence verification

1. Start Figmux and sign into Figma.
2. Close the app fully.
3. Re-open Figmux.
4. Confirm the session remains authenticated.

If sessions are lost, verify `src/main.js` still uses `partition: "persist:figmux"` and the app ID remains `com.figmux.app`.
