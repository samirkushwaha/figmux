from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _verify_ldd(bundle_dir: Path) -> None:
    plugin_path = bundle_dir / "_internal" / "PyQt6" / "Qt6" / "plugins" / "imageformats" / "libqtiff.so"
    result = subprocess.run(["ldd", str(plugin_path)], check=True, capture_output=True, text=True)
    expected_path = (bundle_dir / "_internal" / "PyQt6" / "Qt6" / "lib" / "libtiff.so.5").resolve()
    resolved_path = None
    for line in result.stdout.splitlines():
        if "libtiff.so.5" not in line or "=>" not in line:
            continue
        resolved_token = line.split("=>", 1)[1].strip().split(" ", 1)[0]
        if resolved_token != "not":
            resolved_path = Path(resolved_token).resolve()
        break

    if resolved_path != expected_path:
        raise RuntimeError(
            "Bundled libqtiff.so did not resolve libtiff.so.5 from the AppImage payload.\n"
            f"Expected path: {expected_path}\n"
            f"Resolved path: {resolved_path}\n"
            f"ldd output:\n{result.stdout}"
        )


def _verify_qt_tiff(bundle_dir: Path) -> None:
    qt_root = bundle_dir / "_internal" / "PyQt6" / "Qt6"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_PLUGIN_PATH"] = str(qt_root / "plugins")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(qt_root / "plugins" / "platforms")
    os.environ.setdefault("XDG_RUNTIME_DIR", tempfile.mkdtemp(prefix="figmux-xdg-runtime-"))

    sys.path.insert(0, str(bundle_dir / "_internal"))

    from PyQt6.QtGui import QColor, QGuiApplication, QImage, QImageReader

    app = QGuiApplication([])
    available_formats = {bytes(fmt).decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()}
    if "tiff" not in available_formats and "tif" not in available_formats:
        raise RuntimeError(f"Qt did not report TIFF support. Available formats: {sorted(available_formats)}")

    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ff4f00"))

    with tempfile.TemporaryDirectory(prefix="figmux-tiff-smoke-") as tmpdir:
        tiff_path = Path(tmpdir) / "smoke.tiff"
        if not image.save(str(tiff_path), "TIFF"):
            raise RuntimeError("Qt failed to save a TIFF using the bundled plugin.")

        reader = QImageReader(str(tiff_path))
        loaded = reader.read()
        if loaded.isNull():
            raise RuntimeError(f"Qt failed to read the TIFF it just wrote: {reader.errorString()}")

    app.quit()


def main() -> int:
    bundle_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/figmux")
    bundle_dir = bundle_dir.resolve()

    if not bundle_dir.exists():
        return _fail(f"Bundle directory does not exist: {bundle_dir}")

    try:
        _verify_ldd(bundle_dir)
        _verify_qt_tiff(bundle_dir)
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc))

    print(f"Verified TIFF support in {bundle_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
