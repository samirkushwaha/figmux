from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QDialog,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

from figmux.app_logging import log_event
from figmux.constants import (
    APP_ID,
    APP_NAME,
    AUTH_POPUP_TITLE,
    CLOSED_TABS_LIMIT,
    FIGMA_RECENTS,
    SESSION_STATE_FILE,
    TITLEBAR_HEIGHT,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
)
from figmux.session import SessionState, SessionTabState, load_session, save_session
from figmux.updater import PendingUpdate
from figmux.url_policy import can_restore_url
from figmux.web import FigmuxPage, FigmuxWebView, WindowOpenTarget, configure_profile


@dataclass(slots=True)
class TabState:
    id: str
    view: FigmuxWebView
    page: FigmuxPage
    title: str
    url: str
    is_loading: bool = False
    can_go_back: bool = False
    can_go_forward: bool = False


class ToastOverlay(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self.title_label = QLabel(self)
        self.message_label = QLabel(self)
        self.title_label.setObjectName("toastTitle")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_toast(self, title: str, message: str, duration_ms: int = 5200) -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.adjustSize()
        self.setVisible(True)
        self.raise_()
        self.timer.start(max(2000, duration_ms))


class WindowButton(QPushButton):
    def __init__(self, text: str, tooltip: str, parent: QWidget):
        super().__init__(text, parent)
        self.setToolTip(tooltip)
        self.setFixedSize(36, 28)


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.drag_active = False
        self.drag_offset = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(6)

        self.label = QLabel(APP_NAME, self)
        self.label.setObjectName("titleBrand")
        self.label.setMinimumWidth(104)
        layout.addWidget(self.label)

        self.tab_bar = QTabBar(self)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.tab_bar, 1)

        self.add_button = QPushButton("+", self)
        self.add_button.setObjectName("addTabButton")
        self.add_button.setFixedSize(30, 28)
        self.add_button.setToolTip("New tab")
        layout.addWidget(self.add_button)

        self.min_button = WindowButton("~", "Minimize", self)
        self.max_button = WindowButton("^", "Maximize", self)
        self.close_button = WindowButton("x", "Close", self)
        self.close_button.setObjectName("closeButton")
        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.childAt(event.position().toPoint()) in {self, self.label}:
            self.window.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.childAt(event.position().toPoint()) in {self, self.label}:
            self.drag_active = True
            self.drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_active and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_active = False
        super().mouseReleaseEvent(event)


class AuthPopupWindow(QMainWindow):
    def __init__(self, title: str, view: FigmuxWebView):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(960, 720)
        self.setCentralWidget(view)


class UpdateReadyDialog(QDialog):
    def __init__(self, pending: PendingUpdate, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Update Ready")
        self.setModal(True)
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("A new update is ready to install", self)
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)

        description = QLabel(
            f"Figmux version {pending.version} has been downloaded and will be automatically installed on exit",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        changelog_heading = QLabel("Changelog", self)
        changelog_heading.setObjectName("updateDialogHeading")
        layout.addWidget(changelog_heading)

        changelog = QPlainTextEdit(self)
        changelog.setReadOnly(True)
        changelog.setPlainText(pending.changelog or "No changelog was provided for this release.")
        changelog.setObjectName("updateDialogChangelog")
        layout.addWidget(changelog, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.restart_button = QPushButton("Restart now", self)
        self.dismiss_button = QPushButton("Got it", self)
        button_row.addWidget(self.restart_button)
        button_row.addWidget(self.dismiss_button)
        layout.addLayout(button_row)


class MainWindow(QMainWindow):
    def __init__(self, logger, font_helper, updater):
        super().__init__()
        self.logger = logger
        self.font_helper = font_helper
        self.updater = updater
        self.profile = self._build_profile()
        self.tab_counter = itertools.count(1)
        self.tabs: dict[str, TabState] = {}
        self.tab_order: list[str] = []
        self.closed_tabs: deque[tuple[str, str, int]] = deque(maxlen=CLOSED_TABS_LIMIT)
        self.popup_windows: list[AuthPopupWindow] = []
        self.update_dialog: UpdateReadyDialog | None = None
        self._relaunch_after_update = False
        self.shutting_down = False
        self.persist_timer = QTimer(self)
        self.persist_timer.setSingleShot(True)
        self.persist_timer.timeout.connect(self.persist_session)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)

        self.stack = QStackedWidget(self)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.toast = ToastOverlay(self)
        self._apply_styles()
        self._wire_window_controls()
        self._wire_tab_strip()
        self._install_shortcuts()
        self.updater.updateReady.connect(self._on_update_ready)
        self.restore_session()

    def _build_profile(self) -> QWebEngineProfile:
        base_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        profile_root = base_dir / "web-profile"
        profile = QWebEngineProfile(APP_ID, self)
        configure_profile(profile, profile_root, self.logger)
        return profile

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
              background: #11151b;
              color: #eef2f8;
            }
            #titleBrand {
              color: #d9e4f5;
              font-weight: 600;
              padding-left: 2px;
            }
            TitleBar, QTabBar {
              background: #161d27;
            }
            QTabBar::tab {
              background: #202a38;
              color: #d5dde8;
              border-radius: 8px;
              padding: 6px 14px;
              margin-right: 4px;
              min-width: 120px;
              max-width: 260px;
            }
            QTabBar::tab:selected {
              background: #2f4158;
            }
            QPushButton {
              background: #233041;
              color: #eff5ff;
              border: none;
              border-radius: 8px;
              padding: 4px 8px;
            }
            QPushButton:hover {
              background: #32475f;
            }
            #closeButton:hover {
              background: #bb3e3e;
            }
            #addTabButton {
              font-size: 18px;
              font-weight: 600;
            }
            #toast {
              background: rgba(20, 28, 40, 235);
              border: 1px solid rgba(255, 255, 255, 28);
              border-radius: 12px;
              color: #eff5ff;
            }
            #toastTitle {
              font-weight: 600;
            }
            #updateDialogTitle {
              font-size: 20px;
              font-weight: 700;
              color: #eff5ff;
            }
            #updateDialogHeading {
              font-size: 12px;
              font-weight: 700;
              letter-spacing: 0.08em;
              color: #bccadf;
              text-transform: uppercase;
            }
            #updateDialogChangelog {
              background: #0f141c;
              border: 1px solid rgba(255, 255, 255, 0.08);
              border-radius: 10px;
              color: #e8eef9;
              padding: 10px;
            }
            """
        )

    def _wire_window_controls(self) -> None:
        self.title_bar.min_button.clicked.connect(self.showMinimized)
        self.title_bar.max_button.clicked.connect(self.toggle_maximized)
        self.title_bar.close_button.clicked.connect(self.close)

    def _wire_tab_strip(self) -> None:
        bar = self.title_bar.tab_bar
        bar.currentChanged.connect(self._on_current_tab_changed)
        bar.tabCloseRequested.connect(self._on_tab_close_requested)
        bar.tabMoved.connect(self._on_tab_moved)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._open_tab_context_menu)
        self.title_bar.add_button.clicked.connect(self.open_new_tab_at_end)

    def _install_shortcuts(self) -> None:
        for sequence, callback in (
            ("Ctrl+T", self.open_new_tab_at_end),
            ("Ctrl+W", self.close_active_tab),
            ("Ctrl+Tab", self.cycle_next_tab),
            ("Ctrl+Shift+Tab", self.cycle_previous_tab),
            ("Ctrl+Shift+T", self.reopen_closed_tab),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)

    def _next_tab_id(self) -> str:
        return f"tab-{next(self.tab_counter)}"

    def _session_path(self) -> Path:
        base_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        return base_dir / SESSION_STATE_FILE

    def _update_titlebar_buttons(self) -> None:
        self.title_bar.max_button.setText("[]" if self.isMaximized() else "^")

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._update_titlebar_buttons()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = min(380, self.width() - 24)
        self.toast.setGeometry(QRect(self.width() - width - 16, TITLEBAR_HEIGHT + 14, width, self.toast.height() or 90))

    def request_window_target(self, source_tab_id: str, mode: str, url: str) -> WindowOpenTarget | None:
        if mode == "popup":
            popup = self._create_popup_window(source_tab_id)
            return WindowOpenTarget(page=popup.centralWidget().page(), mode=mode)
        if mode == "child-tab":
            source_index = self.tab_order.index(source_tab_id) if source_tab_id in self.tab_order else len(self.tab_order) - 1
            tab = self.create_tab(url=url or FIGMA_RECENTS, activate=True, insert_index=source_index + 1)
            return WindowOpenTarget(page=tab.page, mode=mode)
        return None

    def _create_page(self, tab_id: str, source_tab_id: str | None = None) -> FigmuxPage:
        page = FigmuxPage(self, self.profile, tab_id=tab_id, logger=self.logger, source_tab_id=source_tab_id)
        page.externalUrlRequested.connect(self._open_external_url)
        page.inputDebugMessage.connect(self._handle_input_debug)
        return page

    def _build_tab(self, tab_id: str, url: str, title: str, source_tab_id: str | None = None) -> TabState:
        page = self._create_page(tab_id, source_tab_id=source_tab_id)
        view = FigmuxWebView(page, self)
        tab = TabState(id=tab_id, view=view, page=page, title=title or "Figma", url=url or FIGMA_RECENTS)
        page.titleChanged.connect(lambda value, tid=tab_id: self._on_tab_title_changed(tid, value))
        page.urlChanged.connect(lambda value, tid=tab_id: self._on_tab_url_changed(tid, value))
        page.loadStarted.connect(lambda tid=tab_id: self._on_tab_load_started(tid))
        page.loadFinished.connect(lambda ok, tid=tab_id: self._on_tab_load_finished(tid, ok))
        page.windowCloseRequested.connect(lambda tid=tab_id: self.close_tab(tid))
        return tab

    def create_tab(self, url: str = FIGMA_RECENTS, activate: bool = True, insert_index: int | None = None, title: str = "Figma") -> TabState:
        tab_id = self._next_tab_id()
        tab = self._build_tab(tab_id, url, title)
        if insert_index is None:
            insert_index = len(self.tab_order)
        insert_index = max(0, min(insert_index, len(self.tab_order)))
        self.tabs[tab_id] = tab
        self.tab_order.insert(insert_index, tab_id)
        self.stack.insertWidget(insert_index, tab.view)
        self.title_bar.tab_bar.insertTab(insert_index, title)
        self.title_bar.tab_bar.setTabData(insert_index, tab_id)
        self.title_bar.tab_bar.setTabToolTip(insert_index, url)
        tab.view.setUrl(QUrl(url))
        tab.page.setZoomFactor(1.0)
        if activate:
            self.activate_tab(tab_id)
        self.queue_persist_session()
        log_event(self.logger, "tab_created", tab_id=tab_id, url=url, insert_index=insert_index)
        return tab

    def open_new_tab_at_end(self) -> None:
        self.create_tab(url=FIGMA_RECENTS, activate=True, insert_index=len(self.tab_order))

    def activate_tab(self, tab_id: str) -> None:
        if tab_id not in self.tabs:
            return
        index = self.tab_order.index(tab_id)
        self.title_bar.tab_bar.blockSignals(True)
        self.title_bar.tab_bar.setCurrentIndex(index)
        self.title_bar.tab_bar.blockSignals(False)
        self.stack.setCurrentWidget(self.tabs[tab_id].view)
        self._update_window_title(tab_id)
        self.queue_persist_session()
        log_event(self.logger, "tab_activated", tab_id=tab_id, index=index)

    def close_active_tab(self) -> None:
        tab_id = self.active_tab_id
        if tab_id:
            self.close_tab(tab_id)

    @property
    def active_tab_id(self) -> str | None:
        current_index = self.title_bar.tab_bar.currentIndex()
        if current_index < 0 or current_index >= len(self.tab_order):
            return None
        return self.tab_order[current_index]

    def close_tab(self, tab_id: str | None) -> None:
        if not tab_id or tab_id not in self.tabs:
            return
        self._destroy_tab(tab_id, remember=True)
        if not self.tab_order and not self.shutting_down:
            self.create_tab()
        elif self.tab_order:
            next_index = min(self.title_bar.tab_bar.currentIndex(), len(self.tab_order) - 1)
            self.activate_tab(self.tab_order[max(next_index, 0)])
        self.queue_persist_session()

    def _destroy_tab(self, tab_id: str, remember: bool) -> None:
        index = self.tab_order.index(tab_id)
        tab = self.tabs.pop(tab_id)
        self.tab_order.pop(index)
        if remember:
            self.closed_tabs.append((tab.url, tab.title, index))
        self.title_bar.tab_bar.removeTab(index)
        self.stack.removeWidget(tab.view)
        tab.page.deleteLater()
        tab.view.deleteLater()
        log_event(self.logger, "tab_closed", tab_id=tab_id, index=index, url=tab.url)

    def reopen_closed_tab(self) -> None:
        if not self.closed_tabs:
            return
        url, title, index = self.closed_tabs.pop()
        self.create_tab(url=url, title=title, insert_index=index, activate=True)
        log_event(self.logger, "tab_reopened", url=url, insert_index=index)

    def cycle_next_tab(self) -> None:
        self._cycle_tabs(backwards=False)

    def cycle_previous_tab(self) -> None:
        self._cycle_tabs(backwards=True)

    def _cycle_tabs(self, backwards: bool) -> None:
        if len(self.tab_order) < 2:
            return
        current_index = self.title_bar.tab_bar.currentIndex()
        if backwards:
            next_index = (current_index - 1) % len(self.tab_order)
        else:
            next_index = (current_index + 1) % len(self.tab_order)
        self.activate_tab(self.tab_order[next_index])

    def _on_current_tab_changed(self, index: int) -> None:
        if index < 0 or index >= len(self.tab_order):
            return
        tab_id = self.tab_order[index]
        self.stack.setCurrentWidget(self.tabs[tab_id].view)
        self._update_window_title(tab_id)
        self.queue_persist_session()

    def _on_tab_close_requested(self, index: int) -> None:
        if 0 <= index < len(self.tab_order):
            self.close_tab(self.tab_order[index])

    def _on_tab_moved(self, from_index: int, to_index: int) -> None:
        if from_index == to_index:
            return
        tab_id = self.tab_order.pop(from_index)
        self.tab_order.insert(to_index, tab_id)
        widget = self.stack.widget(from_index)
        self.stack.removeWidget(widget)
        self.stack.insertWidget(to_index, widget)
        for index, item_tab_id in enumerate(self.tab_order):
            self.title_bar.tab_bar.setTabData(index, item_tab_id)
        self.queue_persist_session()
        log_event(self.logger, "tab_moved", tab_id=tab_id, from_index=from_index, to_index=to_index)

    def _open_tab_context_menu(self, point) -> None:
        index = self.title_bar.tab_bar.tabAt(point)
        if index < 0:
            return
        tab_id = self.tab_order[index]
        menu = QMenu(self)
        reopen = QAction("Reopen Closed Tab", self)
        reopen.triggered.connect(self.reopen_closed_tab)
        close = QAction("Close Tab", self)
        close.triggered.connect(lambda: self.close_tab(tab_id))
        menu.addAction(reopen)
        menu.addAction(close)
        menu.exec(self.title_bar.tab_bar.mapToGlobal(point))

    def _on_tab_title_changed(self, tab_id: str, value: str) -> None:
        if tab_id not in self.tabs:
            return
        title = (value or "").strip() or "Figma"
        self.tabs[tab_id].title = title
        index = self.tab_order.index(tab_id)
        self.title_bar.tab_bar.setTabText(index, title)
        self._update_window_title(tab_id)
        self.queue_persist_session()
        log_event(self.logger, "tab_title_changed", tab_id=tab_id, title=title)

    def _on_tab_url_changed(self, tab_id: str, value: QUrl) -> None:
        if tab_id not in self.tabs:
            return
        url = value.toString()
        self.tabs[tab_id].url = url
        self.tabs[tab_id].can_go_back = self.tabs[tab_id].page.history().canGoBack()
        self.tabs[tab_id].can_go_forward = self.tabs[tab_id].page.history().canGoForward()
        index = self.tab_order.index(tab_id)
        self.title_bar.tab_bar.setTabToolTip(index, url)
        if tab_id == self.active_tab_id:
            self._update_window_title(tab_id)
        self.queue_persist_session()
        log_event(self.logger, "tab_url_changed", tab_id=tab_id, url=url)

    def _on_tab_load_started(self, tab_id: str) -> None:
        if tab_id not in self.tabs:
            return
        self.tabs[tab_id].is_loading = True
        log_event(self.logger, "tab_load_started", tab_id=tab_id, url=self.tabs[tab_id].url)

    def _on_tab_load_finished(self, tab_id: str, ok: bool) -> None:
        if tab_id not in self.tabs:
            return
        tab = self.tabs[tab_id]
        tab.is_loading = False
        tab.can_go_back = tab.page.history().canGoBack()
        tab.can_go_forward = tab.page.history().canGoForward()
        tab.page.inject_input_debug()
        log_event(self.logger, "tab_load_finished", tab_id=tab_id, ok=ok, url=tab.url)

    def _create_popup_window(self, source_tab_id: str | None = None) -> AuthPopupWindow:
        popup_id = self._next_tab_id()
        page = self._create_page(popup_id, source_tab_id=source_tab_id)
        view = FigmuxWebView(page, self)
        view.page().windowCloseRequested.connect(lambda: self._close_popup(view.window()))
        popup = AuthPopupWindow(AUTH_POPUP_TITLE, view)
        popup.destroyed.connect(lambda: self._forget_popup(popup))
        popup.show()
        self.popup_windows.append(popup)
        log_event(self.logger, "auth_popup_created", source_tab_id=source_tab_id)
        return popup

    def _close_popup(self, window) -> None:
        if isinstance(window, AuthPopupWindow):
            window.close()

    def _forget_popup(self, popup: AuthPopupWindow) -> None:
        self.popup_windows = [item for item in self.popup_windows if item is not popup]

    def _open_external_url(self, url: str) -> None:
        if not url:
            return
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))
        self.show_toast("Opened in browser", url)

    def show_toast(self, title: str, message: str, duration_ms: int = 5200) -> None:
        self.toast.show_toast(title, message, duration_ms)
        width = min(380, self.width() - 24)
        self.toast.setGeometry(QRect(self.width() - width - 16, TITLEBAR_HEIGHT + 14, width, self.toast.sizeHint().height()))

    def _handle_input_debug(self, payload: dict) -> None:
        log_event(self.logger, "input_debug", **payload)

    def _on_update_ready(self, pending: PendingUpdate) -> None:
        if self.update_dialog:
            self.update_dialog.close()
            self.update_dialog.deleteLater()
        dialog = UpdateReadyDialog(pending, self)
        dialog.restart_button.clicked.connect(self._restart_to_install_update)
        dialog.dismiss_button.clicked.connect(dialog.accept)
        dialog.finished.connect(lambda _: self._clear_update_dialog())
        self.update_dialog = dialog
        dialog.open()

    def _clear_update_dialog(self) -> None:
        if self.update_dialog:
            self.update_dialog.deleteLater()
            self.update_dialog = None

    def _restart_to_install_update(self) -> None:
        self._relaunch_after_update = True
        if self.update_dialog:
            self.update_dialog.close()
        self.close()

    def _update_window_title(self, tab_id: str | None) -> None:
        if not tab_id or tab_id not in self.tabs:
            self.setWindowTitle(APP_NAME)
            return
        tab = self.tabs[tab_id]
        title = tab.title or "Figma"
        self.setWindowTitle(f"{title} - {APP_NAME}")

    def queue_persist_session(self) -> None:
        self.persist_timer.start(250)

    def persist_session(self) -> None:
        tabs = [
            SessionTabState(id=tab_id, url=self.tabs[tab_id].url, title=self.tabs[tab_id].title)
            for tab_id in self.tab_order
            if can_restore_url(self.tabs[tab_id].url)
        ]
        state = SessionState(active_tab_id=self.active_tab_id, tabs=tabs)
        save_session(self._session_path(), state)
        log_event(self.logger, "session_persisted", tab_count=len(tabs), active_tab_id=self.active_tab_id)

    def restore_session(self) -> None:
        state = load_session(self._session_path())
        restored_map: dict[str, str] = {}
        for item in state.tabs:
            tab = self.create_tab(url=item.url, activate=False, insert_index=len(self.tab_order), title=item.title)
            restored_map[item.id] = tab.id
        if not restored_map:
            tab = self.create_tab(url=FIGMA_RECENTS, activate=True, insert_index=0)
            restored_map[tab.id] = tab.id
        elif state.active_tab_id and state.active_tab_id in restored_map:
            self.activate_tab(restored_map[state.active_tab_id])
        else:
            first_tab_id = next(iter(restored_map.values()))
            self.activate_tab(first_tab_id)
        log_event(self.logger, "session_restored", restored_count=len(restored_map), requested_active_tab_id=state.active_tab_id)

    def closeEvent(self, event) -> None:
        self.shutting_down = True
        self.persist_session()
        self.updater.install_on_exit(relaunch=self._relaunch_after_update)
        for popup in list(self.popup_windows):
            popup.close()
        for tab_id in list(self.tab_order):
            if tab_id in self.tabs:
                self._destroy_tab(tab_id, remember=False)
        self.font_helper.stop()
        super().closeEvent(event)
