from __future__ import annotations

import json
import os
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
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
from figmux.constants import (
    FIGMA_RECENTS,
    WINDOWS_CHROMIUM_USER_AGENT,
    WINDOWS_PLATFORM,
    WINDOWS_USER_AGENT_DATA_BRANDS,
)
from figmux.debug_js import DOM_EVENT_DEBUG_JS
from figmux.url_policy import (
    is_allowed_auth_or_figma_url,
    is_blocked_embedded_google_sign_in_url,
    is_figma_url,
    is_oauth_url,
    should_open_auth_popup,
)


def configure_profile(profile: QWebEngineProfile, storage_root, logger) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(storage_root / "storage"))
    profile.setCachePath(str(storage_root / "cache"))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    profile.setPersistentPermissionsPolicy(
        QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
    )
    profile.setHttpUserAgent(WINDOWS_CHROMIUM_USER_AGENT)
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


def build_figma_navigator_spoof_script() -> QWebEngineScript:
    brands = json.dumps(list(WINDOWS_USER_AGENT_DATA_BRANDS))
    source = f"""
(() => {{
  const hostname = (window.location.hostname || "").toLowerCase();
  const pathname = window.location.pathname || "/";
  const isFigmaHost = hostname === "figma.com" || hostname.endsWith(".figma.com");
  const authPrefixes = ["/login", "/signup", "/oauth"];
  const googleAuthHosts = new Set([
    "accounts.google.com",
    "accounts.youtube.com",
    "oauth2.googleapis.com",
    "apis.google.com"
  ]);
  const isGoogleAuthHost =
    googleAuthHosts.has(hostname) ||
    hostname === "google.com" ||
    hostname.endsWith(".google.com") ||
    hostname.endsWith(".googleusercontent.com");
  const isFigmaAuthPath = isFigmaHost && authPrefixes.some((prefix) => pathname.startsWith(prefix));
  const shouldSpoof = isGoogleAuthHost || isFigmaHost || isFigmaAuthPath;
  if (!shouldSpoof) {{
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
  const brands = {brands};
  const languages = ["en-US", "en"];
  const appVersion = windowsUserAgent.replace(/^Mozilla\\//, "");
  const baseUserAgentData =
    navigator.userAgentData && typeof navigator.userAgentData === "object"
      ? navigator.userAgentData
      : null;
  const spoofedUserAgentData = {{
    brands,
    mobile: false,
    platform: "Windows",
    getHighEntropyValues: async (hints) => {{
      const values = {{}};
      const requestedHints = Array.isArray(hints) ? hints : [];
      for (const hint of requestedHints) {{
        switch (hint) {{
          case "architecture":
            values.architecture = "x86";
            break;
          case "bitness":
            values.bitness = "64";
            break;
          case "brands":
            values.brands = brands;
            break;
          case "fullVersionList":
            values.fullVersionList = brands.map((brand) => ({{
              brand: brand.brand,
              version: `${{brand.version}}.0.0.0`
            }}));
            break;
          case "mobile":
            values.mobile = false;
            break;
          case "model":
            values.model = "";
            break;
          case "platform":
            values.platform = "Windows";
            break;
          case "platformVersion":
            values.platformVersion = "19.0.0";
            break;
          case "uaFullVersion":
            values.uaFullVersion = "142.0.0.0";
            break;
          case "wow64":
            values.wow64 = false;
            break;
          default:
            break;
        }}
      }}
      return values;
    }},
    toJSON: () => ({{
      brands,
      mobile: false,
      platform: "Windows"
    }})
  }};

  defineGetter(navigatorPrototype, "platform", () => windowsPlatform);
  defineGetter(navigatorPrototype, "userAgent", () => windowsUserAgent);
  defineGetter(navigatorPrototype, "appVersion", () => appVersion);
  defineGetter(navigatorPrototype, "vendor", () => "Google Inc.");
  defineGetter(navigatorPrototype, "language", () => languages[0]);
  defineGetter(navigatorPrototype, "languages", () => languages);
  defineGetter(navigatorPrototype, "webdriver", () => false);
  defineGetter(navigatorPrototype, "userAgentData", () => spoofedUserAgentData);

  try {{
    if (!window.chrome) {{
      window.chrome = {{}};
    }}
    if (!window.chrome.runtime) {{
      window.chrome.runtime = {{}};
    }}
  }} catch (_error) {{
  }}

  if (baseUserAgentData && typeof baseUserAgentData.getHighEntropyValues === "function") {{
    try {{
      baseUserAgentData.getHighEntropyValues = spoofedUserAgentData.getHighEntropyValues;
    }} catch (_error) {{
    }}
  }}
}})();
"""
    script = QWebEngineScript()
    script.setName("figmux-figma-navigator-spoof")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setRunsOnSubFrames(True)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setSourceCode(source)
    return script


@dataclass(slots=True)
class WindowOpenTarget:
    page: QWebEnginePage
    mode: str


class FigmuxPage(QWebEnginePage):
    externalUrlRequested = pyqtSignal(str)
    inputDebugMessage = pyqtSignal(dict)
    embeddedGoogleSignInBlocked = pyqtSignal(str)

    def __init__(self, owner: QObject, profile: QWebEngineProfile, tab_id: str, logger, source_tab_id: str | None = None):
        super().__init__(profile, owner)
        self.owner = owner
        self.tab_id = tab_id
        self.logger = logger
        self.source_tab_id = source_tab_id
        self.debug_enabled = os.environ.get("FIGMUX_INPUT_DEBUG") == "1"
        self.newWindowRequested.connect(self._on_new_window_requested)
        self.navigationRequested.connect(self._on_navigation_requested)
        self.permissionRequested.connect(self._on_permission_requested)
        self.featurePermissionRequested.connect(self._on_feature_permission_requested)
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
        if is_blocked_embedded_google_sign_in_url(requested_url):
            self.embeddedGoogleSignInBlocked.emit(requested_url)
            log_event(
                self.logger,
                "embedded_google_sign_in_blocked",
                tab_id=self.tab_id,
                url=requested_url,
            )
            return
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
        if self.debug_enabled:
            self.runJavaScript(DOM_EVENT_DEBUG_JS)


class FigmuxWebView(QWebEngineView):
    def __init__(self, page: FigmuxPage, parent=None):
        super().__init__(parent)
        self.setPage(page)
        self.page().setBackgroundColor(self.palette().window().color())
        self.page().fullScreenRequested.connect(self._on_fullscreen_requested)

    def _on_fullscreen_requested(self, request) -> None:
        request.accept()
        window = self.window()
        if window:
            window.setWindowState(window.windowState() | Qt.WindowState.WindowFullScreen)

    def open_external(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
