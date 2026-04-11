# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()
TIFF_BUNDLE_DIR = ROOT / 'build' / 'appimage-tiff-libs'
TIFF_DEST_DIR = 'PyQt6/Qt6/lib'
TIFF_ROOT_LIB = 'libtiff.so.5'


def _parse_ldd_dependencies(binary_path: Path) -> list[Path]:
    result = subprocess.run(
        ['ldd', str(binary_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    dependencies = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if '=>' not in line:
            continue
        _, resolved = line.split('=>', 1)
        resolved = resolved.strip().split(' ', 1)[0]
        if resolved == 'not':
            raise SystemExit(f'Unresolved dependency while inspecting {binary_path}: {line}')
        if resolved.startswith('/'):
            dependencies.append(Path(resolved))
    return dependencies


def _should_bundle_tiff_dependency(path: Path) -> bool:
    name = path.name
    if name.startswith('libQt6'):
        return False
    if name.startswith('ld-linux'):
        return False
    if name.startswith(('libc.so', 'libm.so', 'libdl.so', 'libpthread.so', 'librt.so', 'libgcc_s.so', 'libstdc++.so')):
        return False
    return True


def _find_system_library(name: str) -> Path:
    search_dirs = [
        Path('/lib64'),
        Path('/usr/lib64'),
        Path('/lib/x86_64-linux-gnu'),
        Path('/usr/lib/x86_64-linux-gnu'),
        Path('/lib'),
        Path('/usr/lib'),
    ]
    env_dirs = os.environ.get('FIGMUX_APPIMAGE_LIBRARY_DIRS')
    if env_dirs:
        search_dirs = [Path(value) for value in env_dirs.split(os.pathsep) if value] + search_dirs

    for directory in search_dirs:
        candidate = directory / name
        if candidate.exists():
            return candidate

    raise SystemExit(
        f'Unable to find required TIFF runtime library {name}. '
        'Run the AppImage build in the containerized Ubuntu 22.04 environment.'
    )


def _collect_tiff_binaries() -> list[tuple[str, str]]:
    root_library = _find_system_library(TIFF_ROOT_LIB)
    if TIFF_BUNDLE_DIR.exists():
        shutil.rmtree(TIFF_BUNDLE_DIR)
    TIFF_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    if shutil.which('patchelf') is None:
        raise SystemExit('patchelf is required to bundle TIFF runtime libraries for AppImage builds.')

    queued = [root_library]
    bundled: dict[str, Path] = {}

    while queued:
        source = queued.pop(0)
        if source.name in bundled:
            continue

        destination = TIFF_BUNDLE_DIR / source.name
        shutil.copy2(source, destination)
        subprocess.run(['patchelf', '--set-rpath', '$ORIGIN', str(destination)], check=True)
        bundled[source.name] = destination

        for dependency in _parse_ldd_dependencies(source):
            if _should_bundle_tiff_dependency(dependency):
                queued.append(dependency)

    return [(str(path), TIFF_DEST_DIR) for path in sorted(bundled.values())]


hiddenimports = []
hiddenimports += collect_submodules('PyQt6.QtWebEngineCore')
hiddenimports += collect_submodules('PyQt6.QtWebEngineWidgets')
hiddenimports += collect_submodules('PyQt6.QtWebEngineQuick')
binaries = _collect_tiff_binaries()


a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[],
    binaries=binaries,
    datas=[(str(ROOT / 'assets'), 'assets'), (str(ROOT / 'resources'), 'resources')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='figmux',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / 'assets' / 'com.figmux.app.png')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='figmux',
)
