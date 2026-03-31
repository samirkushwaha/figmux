from __future__ import annotations

import json
import os
from dataclasses import dataclass

from PyQt6.QtCore import QBuffer, QIODevice, QMimeData, QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QClipboard, QColor, QDesktopServices, QGuiApplication, QImage
from PyQt6.QtWebEngineCore import (
    QWebEngineNavigationRequest,
    QWebEnginePage,
    QWebEnginePermission,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from figmux.app_logging import log_event
from figmux.constants import FIGMA_RECENTS, WINDOWS_CHROMIUM_USER_AGENT, WINDOWS_PLATFORM
from figmux.debug_js import CURSOR_SCALE_DEBUG_JS, DOM_EVENT_DEBUG_JS
from figmux.url_policy import (
    is_allowed_auth_or_figma_url,
    is_figma_auth_url,
    is_figma_url,
    is_oauth_url,
    should_open_auth_popup,
)


def build_figma_navigator_spoof_script() -> QWebEngineScript:
    source = f"""
(() => {{
  const hostname = (window.location.hostname || "").toLowerCase();
  const pathname = window.location.pathname || "/";
  const isFigmaHost = hostname === "figma.com" || hostname.endsWith(".figma.com");
  const authPrefixes = ["/login", "/signup", "/oauth"];
  const isAuthPath = authPrefixes.some((prefix) => pathname.startsWith(prefix));
  if (!isFigmaHost || isAuthPath) {{
    return;
  }}

  const defineGetter = (object, key, getter) => {{
    if (!object) {{
      return;
    }}
    try {{
      Object.defineProperty(object, key, {{
        configurable: true,
        enumerable: true,
        get: getter
      }});
    }} catch (_error) {{
    }}
  }};

  const navigatorPrototype = window.Navigator && window.Navigator.prototype;
  const windowsUserAgent = {json.dumps(WINDOWS_CHROMIUM_USER_AGENT)};
  const windowsPlatform = {json.dumps(WINDOWS_PLATFORM)};
  const appVersion = windowsUserAgent.replace(/^Mozilla\\//, "");

  defineGetter(navigatorPrototype, "platform", () => windowsPlatform);
  defineGetter(navigatorPrototype, "userAgent", () => windowsUserAgent);
  defineGetter(navigatorPrototype, "appVersion", () => appVersion);
}})();
"""
    script = QWebEngineScript()
    script.setName("figmux-figma-navigator-spoof")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setRunsOnSubFrames(True)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setSourceCode(source)
    return script


def navigator_spoof_enabled() -> bool:
    return os.environ.get("FIGMUX_DISABLE_NAVIGATOR_SPOOF") != "1"


def configure_profile(profile: QWebEngineProfile, storage_root, logger) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(storage_root / "storage"))
    profile.setCachePath(str(storage_root / "cache"))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    profile.setPersistentPermissionsPolicy(
        QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
    )
    settings = profile.settings()
    for attr in (
        QWebEngineSettings.WebAttribute.LocalStorageEnabled,
        QWebEngineSettings.WebAttribute.JavascriptEnabled,
        QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
        QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
        QWebEngineSettings.WebAttribute.JavascriptCanPaste,
        QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,
        QWebEngineSettings.WebAttribute.PluginsEnabled,
        QWebEngineSettings.WebAttribute.WebGLEnabled,
        QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled,
        QWebEngineSettings.WebAttribute.TouchEventsApiEnabled,
        QWebEngineSettings.WebAttribute.NavigateOnDropEnabled,
    ):
        settings.setAttribute(attr, True)
    log_event(logger, "profile_configured", storage=str(storage_root))


@dataclass(slots=True)
class WindowOpenTarget:
    page: QWebEnginePage
    mode: str


class FigmuxPage(QWebEnginePage):
    externalUrlRequested = pyqtSignal(str)
    inputDebugMessage = pyqtSignal(dict)

    def __init__(self, owner: QObject, profile: QWebEngineProfile, tab_id: str, logger, source_tab_id: str | None = None):
        super().__init__(profile, owner)
        self.owner = owner
        self.tab_id = tab_id
        self.logger = logger
        self.source_tab_id = source_tab_id
        self.input_debug_enabled = os.environ.get("FIGMUX_INPUT_DEBUG") == "1"
        self.cursor_debug_enabled = os.environ.get("FIGMUX_CURSOR_DEBUG") == "1"
        self.newWindowRequested.connect(self._on_new_window_requested)
        self.navigationRequested.connect(self._on_navigation_requested)
        self.permissionRequested.connect(self._on_permission_requested)
        self.featurePermissionRequested.connect(self._on_feature_permission_requested)
        if navigator_spoof_enabled():
            self.scripts().insert(build_figma_navigator_spoof_script())

    def javaScriptConsoleMessage(self, level, message: str, line_number: int, source_id: str) -> None:
        if "[figmux-input-debug]" in message:
            payload = {"tab_id": self.tab_id, "message": message, "line": line_number, "source": source_id}
            prefix, _, raw_json = message.partition("] ")
            if raw_json:
                try:
                    payload.update(json.loads(raw_json))
                except json.JSONDecodeError:
                    payload["raw"] = raw_json
            self.inputDebugMessage.emit(payload)
        super().javaScriptConsoleMessage(level, message, line_number, source_id)

    def _on_navigation_requested(self, request: QWebEngineNavigationRequest) -> None:
        url = request.url().toString()
        if request.isMainFrame() and not is_allowed_auth_or_figma_url(url):
            request.reject()
            self.externalUrlRequested.emit(url)
            log_event(self.logger, "external_link_routed", tab_id=self.tab_id, url=url)
            return
        request.accept()

    def _on_permission_requested(self, permission: QWebEnginePermission) -> None:
        kind = permission.permissionType().name
        origin = permission.origin().toString()
        allowed = False
        if is_figma_url(origin):
            allowed = kind in {"ClipboardReadWrite", "LocalFontsAccess"}
        if allowed:
            permission.grant()
        else:
            permission.deny()
        log_event(self.logger, "permission_request", tab_id=self.tab_id, origin=origin, permission=kind, allowed=allowed)

    def _on_feature_permission_requested(self, security_origin, feature) -> None:
        origin = security_origin.toString()
        allowed = False
        if is_figma_url(origin):
            allowed = feature in {
                QWebEnginePage.Feature.ClipboardReadWrite,
                QWebEnginePage.Feature.LocalFontsAccess,
            }
        policy = (
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            if allowed
            else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )
        self.setFeaturePermission(security_origin, feature, policy)
        log_event(
            self.logger,
            "feature_permission_request",
            tab_id=self.tab_id,
            origin=origin,
            feature=feature.name,
            allowed=allowed,
        )

    def _on_new_window_requested(self, request) -> None:
        requested_url = request.requestedUrl().toString()
        current_url = self.url().toString()
        if should_open_auth_popup(requested_url, current_url):
            target = self.owner.request_window_target(self.tab_id, "popup", requested_url)
        elif is_figma_url(requested_url) or not requested_url:
            target = self.owner.request_window_target(self.tab_id, "child-tab", requested_url or FIGMA_RECENTS)
        else:
            target = None
            self.externalUrlRequested.emit(requested_url)
            log_event(self.logger, "external_popup_routed", tab_id=self.tab_id, url=requested_url)
        if target:
            request.openIn(target.page)
            log_event(self.logger, "new_window_target_created", tab_id=self.tab_id, url=requested_url, mode=target.mode)

    def inject_input_debug(self) -> None:
        if self.input_debug_enabled:
            self.runJavaScript(DOM_EVENT_DEBUG_JS)

    def inject_cursor_debug(self) -> None:
        if self.cursor_debug_enabled:
            self.runJavaScript(CURSOR_SCALE_DEBUG_JS)


def normalize_clipboard_image_for_paste(page: FigmuxPage, *, trigger_event: str) -> bool:
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        _log_clipboard_debug_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=[],
            has_image=False,
            has_text=False,
            has_html=False,
            has_urls=False,
            image_is_null=True,
            image_source_format=None,
            attempted_image_formats=[],
            augmentation_status="skipped_no_clipboard",
        )
        return False

    mime_data = clipboard.mimeData()
    if mime_data is None:
        _log_clipboard_debug_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=[],
            has_image=False,
            has_text=False,
            has_html=False,
            has_urls=False,
            image_is_null=True,
            image_source_format=None,
            attempted_image_formats=[],
            augmentation_status="skipped_no_mime_data",
        )
        return False

    formats = [format_name.lower() for format_name in mime_data.formats()]
    format_set = set(formats)
    image = clipboard.image()
    image_is_null = image.isNull()
    image_source_format = "qt-image" if not image_is_null else None
    attempted_image_formats: list[str] = []
    stripped_formats = [format_name for format_name in formats if format_name in _IMAGE_PASTE_STRIP_FORMATS]

    if "image/png" in format_set and not stripped_formats:
        _log_clipboard_debug_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=formats,
            has_image=mime_data.hasImage(),
            has_text=mime_data.hasText(),
            has_html=mime_data.hasHtml(),
            has_urls=mime_data.hasUrls(),
            image_is_null=image_is_null,
            image_source_format=image_source_format,
            attempted_image_formats=attempted_image_formats,
            stripped_formats=stripped_formats,
            augmentation_status="skipped_already_png",
        )
        return False

    if image_is_null:
        image, image_source_format, attempted_image_formats = _decode_image_from_mime_data(mime_data)
        image_is_null = image.isNull()

    if image_is_null:
        _log_clipboard_debug_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=formats,
            has_image=mime_data.hasImage(),
            has_text=mime_data.hasText(),
            has_html=mime_data.hasHtml(),
            has_urls=mime_data.hasUrls(),
            image_is_null=True,
            image_source_format=image_source_format,
            attempted_image_formats=attempted_image_formats,
            stripped_formats=stripped_formats,
            augmentation_status="skipped_no_extractable_image",
        )
        return False

    buffer = QBuffer(page)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        _log_clipboard_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=formats,
            has_image=mime_data.hasImage(),
            has_text=mime_data.hasText(),
            has_html=mime_data.hasHtml(),
            has_urls=mime_data.hasUrls(),
            image_is_null=False,
            image_source_format=image_source_format,
            attempted_image_formats=attempted_image_formats,
            stripped_formats=stripped_formats,
            augmentation_status="failed_open_png_buffer",
        )
        return False
    if not image.save(buffer, "PNG"):
        _log_clipboard_event(
            page,
            "clipboard_paste_intercepted",
            tab_id=page.tab_id,
            trigger_event=trigger_event,
            formats=formats,
            has_image=mime_data.hasImage(),
            has_text=mime_data.hasText(),
            has_html=mime_data.hasHtml(),
            has_urls=mime_data.hasUrls(),
            image_is_null=False,
            image_source_format=image_source_format,
            attempted_image_formats=attempted_image_formats,
            stripped_formats=stripped_formats,
            augmentation_status="failed_encode_png",
        )
        return False

    normalized_mime_data = QMimeData()
    for format_name in mime_data.formats():
        if format_name.lower() in _IMAGE_PASTE_STRIP_FORMATS:
            continue
        normalized_mime_data.setData(format_name, mime_data.data(format_name))
    normalized_mime_data.setData("image/png", buffer.data())
    normalized_mime_data.setImageData(image)
    clipboard.setMimeData(normalized_mime_data, QClipboard.Mode.Clipboard)

    _log_clipboard_debug_event(
        page,
        "clipboard_paste_intercepted",
        tab_id=page.tab_id,
        trigger_event=trigger_event,
        formats=formats,
        has_image=mime_data.hasImage(),
        has_text=mime_data.hasText(),
        has_html=mime_data.hasHtml(),
        has_urls=mime_data.hasUrls(),
        image_is_null=False,
        image_source_format=image_source_format,
        attempted_image_formats=attempted_image_formats,
        stripped_formats=stripped_formats,
        augmentation_status="sanitized" if stripped_formats else "augmented",
    )
    _log_clipboard_debug_event(
        page,
        "clipboard_image_normalized_for_paste",
        tab_id=page.tab_id,
        operation="sanitized" if stripped_formats else "augmented",
        trigger_event=trigger_event,
        original_formats=formats,
        preserved_formats=[format_name for format_name in formats if format_name not in _IMAGE_PASTE_STRIP_FORMATS],
        added_formats=["image/png"],
        image_source_format=image_source_format,
        stripped_formats=stripped_formats,
    )
    return True


def _log_clipboard_debug_event(page: FigmuxPage, message: str, **payload) -> None:
    if page.input_debug_enabled:
        log_event(page.logger, message, **payload)


def _log_clipboard_event(page: FigmuxPage, message: str, **payload) -> None:
    log_event(page.logger, message, **payload)


def _decode_image_from_mime_data(mime_data: QMimeData) -> tuple[QImage, str | None, list[str]]:
    attempted_formats: list[str] = []
    for format_name in mime_data.formats():
        lowered_format = format_name.lower()
        if not lowered_format.startswith("image/") or lowered_format == "image/png":
            continue
        attempted_formats.append(lowered_format)
        image = QImage.fromData(mime_data.data(format_name))
        if not image.isNull():
            return image, lowered_format, attempted_formats
    return QImage(), None, attempted_formats


_IMAGE_PASTE_STRIP_FORMATS = {
    "chromium/x-source-url",
    "chromium/x-internal-source-rfh-token",
    "text/uri-list",
}


class FigmuxWebView(QWebEngineView):
    def __init__(self, page: FigmuxPage, parent=None):
        super().__init__(parent)
        self.setPage(page)
        self.page().setBackgroundColor(QColor("#2C2C2A"))
        self.page().fullScreenRequested.connect(self._on_fullscreen_requested)

    def _on_fullscreen_requested(self, request) -> None:
        request.accept()
        window = self.window()
        if window:
            window.setWindowState(window.windowState() | Qt.WindowState.WindowFullScreen)

    def open_external(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
