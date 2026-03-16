# Figmux

Figmux is a Linux desktop wrapper for [Figma](https://www.figma.com) built with Python, PyQt6, and PyQt6-WebEngine.

This repository now contains the mainline Qt application. The previous Electron app has been preserved separately as `figmux-deprecated`.

## What It Does

- Opens Figma in a dedicated desktop window with a custom tab strip
- Keeps Figma and auth flows inside the app
- Routes non-Figma links to the system browser
- Persists tabs, cookies, storage, and active session between launches
- Bundles `figma-agent-linux` for local font support in Flatpak and AppImage builds
- Ships first-class Flatpak and AppImage build paths

## Project Layout

- `main.py`: top-level entrypoint
- `figmux/`: application package
- `flatpak/`: Flatpak launcher, manifest, and desktop metadata
- `scripts/`: local run, packaging, and release helpers
- `assets/`: app icons
- `resources/`: local bundled resources

## Local Setup

```bash
python3 -m ensurepip --upgrade
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[build]
```

## Local Run

```bash
. .venv/bin/activate
python main.py
```

CLI entry point:

```bash
. .venv/bin/activate
figmux
```

Optional input debug logging:

```bash
. .venv/bin/activate
FIGMUX_INPUT_DEBUG=1 python main.py
```

Optional local `figma-agent` install:

```bash
bash scripts/install-figma-agent.sh
```

## Flatpak

Install runtimes:

```bash
flatpak install flathub org.kde.Platform//6.10 org.kde.Sdk//6.10 com.riverbankcomputing.PyQt.BaseApp//6.10
```

Build, install, and run:

```bash
bash scripts/flatpak-build.sh
bash scripts/flatpak-install.sh
bash scripts/flatpak-run.sh
```

Direct run:

```bash
flatpak run com.figmux.app
```

## AppImage

Build:

```bash
bash scripts/appimage-build.sh
```

Run:

```bash
chmod +x dist/figmux-x86_64.AppImage
./dist/figmux-x86_64.AppImage
```

## Releases

Build versioned release artifacts:

```bash
bash scripts/release-all.sh --bump-patch
```

Generated artifacts:

- `dist/figmux-<version>-x86_64.flatpak`
- `dist/figmux-<version>-x86_64.flatpak.sha256`
- `dist/figmux-<version>-x86_64.AppImage`
- `dist/figmux-<version>-x86_64.AppImage.sha256`

## Release Checklist

```bash
python -m pip install -e .[build]
bash scripts/release-all.sh --bump-patch
git status
git add .
git commit -m "Release v<version>"
git tag v<version>
git push origin main --tags
```

After pushing the tag, create a GitHub Release on `samirkushwaha/figmux` and upload:

- `dist/figmux-<version>-x86_64.flatpak`
- `dist/figmux-<version>-x86_64.flatpak.sha256`
- `dist/figmux-<version>-x86_64.AppImage`
- `dist/figmux-<version>-x86_64.AppImage.sha256`

## Notes

- The current UI is a solid Qt baseline, not the final visual polish target.
- Session/profile storage intentionally starts fresh under `com.figmux.app`.
- `FIGMUX_INPUT_DEBUG=1` remains available for drag/drop and paste instrumentation.

## Legal

- Figmux is an unofficial wrapper and is not affiliated with Figma.
- "Figma" and related marks are trademarks of their respective owners.
- Packaged builds bundle `figma-agent-linux`: <https://github.com/neetly/figma-agent-linux>
