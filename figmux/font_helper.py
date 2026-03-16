from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from PyQt6.QtCore import QObject

from figmux.app_logging import log_event
from figmux.constants import APPIMAGE_FIGMA_AGENT_RELATIVE_PATH, FIGMA_AGENT_VERSION_URL, FLATPAK_FIGMA_AGENT_PATH


class FontHelperService(QObject):
    def __init__(self, logger, project_root: Path):
        super().__init__()
        self.logger = logger
        self.project_root = project_root
        self.process: subprocess.Popen[str] | None = None

    def resolve_binary(self) -> Path | None:
        candidates = [FLATPAK_FIGMA_AGENT_PATH]
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                executable_dir / APPIMAGE_FIGMA_AGENT_RELATIVE_PATH,
                self.project_root / APPIMAGE_FIGMA_AGENT_RELATIVE_PATH,
                self.project_root / "dist" / APPIMAGE_FIGMA_AGENT_RELATIVE_PATH,
            ]
        )
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir) / APPIMAGE_FIGMA_AGENT_RELATIVE_PATH)
        for path in candidates:
            if path.exists():
                return path
        return None

    def probe(self, timeout_seconds: float = 1.2) -> bool:
        try:
            with urlopen(FIGMA_AGENT_VERSION_URL, timeout=timeout_seconds) as response:
                return response.status == 200
        except URLError:
            return False

    def start(self) -> None:
        binary = self.resolve_binary()
        if not binary:
            log_event(self.logger, "figma_agent_missing")
            return
        if self.probe(0.4):
            log_event(self.logger, "figma_agent_already_running", path=str(binary))
            return
        env = os.environ.copy()
        try:
            self.process = subprocess.Popen(
                [str(binary)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
                env=env,
            )
        except OSError as error:
            log_event(self.logger, "figma_agent_start_failed", path=str(binary), error=str(error))
            self.process = None
            return

        for _ in range(6):
            if self.probe(0.4):
                log_event(self.logger, "figma_agent_ready", path=str(binary))
                return
            time.sleep(0.25)
        log_event(self.logger, "figma_agent_unreachable", path=str(binary))

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
        log_event(self.logger, "figma_agent_stopped")
