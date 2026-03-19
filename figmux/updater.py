from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PyQt6.QtCore import QObject, QStandardPaths, pyqtSignal

from figmux import __version__
from figmux.app_logging import log_event
from figmux.constants import APP_NAME, GITHUB_REPO

GITHUB_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
APPIMAGE_ASSET_PATTERN = re.compile(r"figmux-.*-x86_64\.AppImage$", re.IGNORECASE)


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    changelog: str
    asset_name: str
    asset_url: str


@dataclass(slots=True)
class PendingUpdate:
    version: str
    changelog: str
    release_url: str
    download_path: Path
    appimage_path: Path


def _normalize_version(version: str) -> str:
    return version.strip().removeprefix("v").strip()


def _version_key(version: str) -> tuple[int, ...]:
    cleaned = _normalize_version(version)
    parts: list[int] = []
    for part in cleaned.split("."):
        match = re.match(r"(\d+)", part)
        parts.append(int(match.group(1)) if match else 0)
    return tuple(parts)


class AppImageUpdater(QObject):
    updateReady = pyqtSignal(object)

    def __init__(self, logger, parent: QObject | None = None):
        super().__init__(parent)
        self.logger = logger
        self.current_version = __version__
        self.appimage_path = self._resolve_appimage_path()
        self.pending_update: PendingUpdate | None = None
        self._check_started = False
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.appimage_path is not None

    def start(self) -> None:
        if self._check_started:
            return
        self._check_started = True
        if not self.enabled:
            log_event(self.logger, "appimage_update_skipped", reason="not_appimage", current_version=self.current_version)
            return
        worker = threading.Thread(target=self._run_check, name="figmux-appimage-updater", daemon=True)
        worker.start()

    def install_on_exit(self, relaunch: bool) -> bool:
        pending = self.pending_update
        if not pending or not pending.download_path.exists():
            return False

        helper_dir = self._update_dir()
        helper_dir.mkdir(parents=True, exist_ok=True)
        helper_path = helper_dir / "install-update.sh"
        helper_path.write_text(
            """#!/usr/bin/env bash
set -euo pipefail

PID="$1"
TARGET="$2"
SOURCE="$3"
RELAUNCH="$4"

while kill -0 "${PID}" 2>/dev/null; do
  sleep 0.2
done

TARGET_DIR="$(dirname "${TARGET}")"
TMP_TARGET="${TARGET_DIR}/.$(basename "${TARGET}").figmux-update"
cp "${SOURCE}" "${TMP_TARGET}"
chmod +x "${TMP_TARGET}"
mv -f "${TMP_TARGET}" "${TARGET}"
rm -f "${SOURCE}"

if [[ "${RELAUNCH}" == "1" ]]; then
  nohup "${TARGET}" >/dev/null 2>&1 &
fi
""",
            encoding="utf-8",
        )
        helper_path.chmod(helper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        try:
            subprocess.Popen(
                ["/bin/bash", str(helper_path), str(os.getpid()), str(pending.appimage_path), str(pending.download_path), "1" if relaunch else "0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            log_event(
                self.logger,
                "appimage_update_install_schedule_failed",
                error=str(error),
                version=pending.version,
                target=str(pending.appimage_path),
            )
            return False

        log_event(
            self.logger,
            "appimage_update_install_scheduled",
            version=pending.version,
            relaunch=relaunch,
            target=str(pending.appimage_path),
            source=str(pending.download_path),
        )
        return True

    def _resolve_appimage_path(self) -> Path | None:
        appimage = os.environ.get("APPIMAGE", "").strip()
        if not appimage:
            return None
        path = Path(appimage)
        return path if path.exists() else None

    def _update_dir(self) -> Path:
        base_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        return base_dir / "updates"

    def _run_check(self) -> None:
        log_event(self.logger, "appimage_update_check_started", current_version=self.current_version)
        try:
            release = self._fetch_latest_release()
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as error:
            log_event(
                self.logger,
                "appimage_update_check_failed",
                current_version=self.current_version,
                error=str(error),
            )
            return

        log_event(
            self.logger,
            "appimage_update_version_check",
            current_version=self.current_version,
            latest_version=release.version,
        )
        if _version_key(release.version) <= _version_key(self.current_version):
            log_event(
                self.logger,
                "appimage_update_not_needed",
                current_version=self.current_version,
                latest_version=release.version,
            )
            return

        try:
            pending = self._download_release(release)
        except (HTTPError, URLError, OSError) as error:
            log_event(
                self.logger,
                "appimage_update_download_failed",
                current_version=self.current_version,
                latest_version=release.version,
                error=str(error),
            )
            return

        with self._lock:
            self.pending_update = pending
        log_event(
            self.logger,
            "appimage_update_ready",
            current_version=self.current_version,
            latest_version=pending.version,
            path=str(pending.download_path),
        )
        self.updateReady.emit(pending)

    def _fetch_latest_release(self) -> ReleaseInfo:
        request = Request(
            GITHUB_LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_NAME}/{self.current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))

        version = _normalize_version(str(payload.get("tag_name") or payload.get("name") or "").strip())
        if not version:
            raise ValueError("Latest GitHub release did not include a version tag")

        asset = self._select_appimage_asset(payload.get("assets") or [])
        if not asset:
            raise ValueError("Latest GitHub release did not include an AppImage asset")

        return ReleaseInfo(
            version=version,
            changelog=(payload.get("body") or "").strip(),
            asset_name=str(asset["name"]),
            asset_url=str(asset["browser_download_url"]),
        )

    def _select_appimage_asset(self, assets: list[dict]) -> dict | None:
        for asset in assets:
            name = str(asset.get("name") or "")
            if APPIMAGE_ASSET_PATTERN.search(name):
                return asset
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.endswith(".AppImage"):
                return asset
        return None

    def _download_release(self, release: ReleaseInfo) -> PendingUpdate:
        if not self.appimage_path:
            raise OSError("AppImage path is unavailable")

        update_dir = self._update_dir()
        update_dir.mkdir(parents=True, exist_ok=True)
        final_path = update_dir / release.asset_name
        temp_path = update_dir / f"{release.asset_name}.part"

        log_event(
            self.logger,
            "appimage_update_download_started",
            version=release.version,
            url=release.asset_url,
            destination=str(final_path),
        )

        request = Request(
            release.asset_url,
            headers={"User-Agent": f"{APP_NAME}/{self.current_version}"},
        )
        try:
            with urlopen(request, timeout=30) as response, temp_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        temp_path.chmod(0o755)
        temp_path.replace(final_path)
        return PendingUpdate(
            version=release.version,
            changelog=release.changelog,
            release_url=release.asset_url,
            download_path=final_path,
            appimage_path=self.appimage_path,
        )
