# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(__file__).resolve().parent

hiddenimports = []
hiddenimports += collect_submodules("PyQt6.QtWebEngineCore")
hiddenimports += collect_submodules("PyQt6.QtWebEngineWidgets")
hiddenimports += collect_submodules("PyQt6.QtWebEngineQuick")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets"), (str(ROOT / "resources"), "resources")],
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
    name="figmux",
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
    icon=[str(ROOT / "assets" / "com.figmux.app.png")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="figmux",
)
