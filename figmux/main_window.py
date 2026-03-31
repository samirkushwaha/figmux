from __future__ import annotations

import itertools
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QEvent, QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize, QStandardPaths, Qt, QTimer, QUrl, QVariantAnimation
from PyQt6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
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
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEngineProfile

from figmux.app_logging import log_event
from figmux.constants import (
    APP_ID,
    APP_NAME,
    ASSETS_DIR,
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
from figmux.web import FigmuxPage, FigmuxWebView, WindowOpenTarget, configure_profile, normalize_clipboard_image_for_paste


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
    def __init__(self, tooltip: str, parent: QWidget):
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.ArrowCursor)


class SvgIconButton(WindowButton):
    def __init__(
        self,
        icon_path: Path,
        tooltip: str,
        parent: QWidget,
        *,
        icon_size: int = 16,
        button_size: QSize = QSize(32, 32),
        icon_opacity: float = 0.7,
        circle_base_alpha: float = 0.0,
        circle_hover_alpha: float = 0.24,
        circle_pressed_alpha: float = 0.64,
    ):
        super().__init__(tooltip, parent)
        self.icon_renderer = QSvgRenderer(str(icon_path), self)
        self.icon_size = icon_size
        self.icon_opacity = icon_opacity
        self.circle_base_alpha = circle_base_alpha
        self.circle_hover_alpha = circle_hover_alpha
        self.circle_pressed_alpha = circle_pressed_alpha
        self.circle_alpha = circle_base_alpha
        self.circle_animation = QVariantAnimation(self)
        self.circle_animation.setDuration(140)
        self.circle_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.circle_animation.valueChanged.connect(self._on_circle_value_changed)
        self.setFixedSize(button_size)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._animate_circle(self.circle_base_alpha)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self.circle_alpha > 0.001:
            circle_color = QColor(0, 0, 0)
            circle_color.setAlphaF(max(0.0, min(self.circle_alpha, 1.0)))
            diameter = min(self.width(), self.height()) - 4
            circle_rect = QRect(
                (self.width() - diameter) // 2,
                (self.height() - diameter) // 2,
                diameter,
                diameter,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(circle_color)
            painter.drawEllipse(circle_rect)

        icon_rect = QRect(
            (self.width() - self.icon_size) // 2,
            (self.height() - self.icon_size) // 2,
            self.icon_size,
            self.icon_size,
        )
        painter.save()
        painter.setOpacity(self.icon_opacity)
        self.icon_renderer.render(painter, QRectF(icon_rect))
        painter.restore()

    def enterEvent(self, event) -> None:
        self._animate_circle(self.circle_hover_alpha)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_circle(self.circle_base_alpha)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_circle(self.circle_pressed_alpha)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        target = self.circle_hover_alpha if self.rect().contains(event.position().toPoint()) else self.circle_base_alpha
        self._animate_circle(target)

    def _on_circle_value_changed(self, value) -> None:
        self.circle_alpha = float(value)
        self.update()

    def _animate_circle(self, target: float) -> None:
        self.circle_animation.stop()
        self.circle_animation.setStartValue(self.circle_alpha)
        self.circle_animation.setEndValue(target)
        self.circle_animation.start()


class TitleTabBar(QTabBar):
    TAB_MIN_WIDTH = 96
    TAB_MAX_WIDTH = 260
    TAB_HORIZONTAL_PADDING = 20
    TAB_TEXT_ICON_GAP = 12
    TAB_CLOSE_ICON_SIZE = 16
    TAB_FONT_SIZE = 10
    HOVER_FILL_ALPHA = 0.16
    ACTIVE_FILL_ALPHA = 0.24
    ICON_ALPHA = 0.7
    CLOSE_HOVER_CIRCLE_ALPHA = 0.24
    CLOSE_PRESSED_CIRCLE_ALPHA = 0.64
    ANIMATION_MS = 170
    SPINNER_SIZE = 14
    SPINNER_GAP = 8
    REORDER_BAND_PADDING = 8

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.close_icon_renderer = QSvgRenderer(str(ASSETS_DIR / "titlebar-close.svg"), self)
        self.hovered_tab_id: str | None = None
        self.hovered_close_tab_id: str | None = None
        self.pressed_close_tab_id: str | None = None
        self.tab_hover_progress: dict[str, float] = {}
        self.close_icon_progress: dict[str, float] = {}
        self.close_circle_progress: dict[str, float] = {}
        self.open_progress: dict[str, float] = {}
        self.close_progress: dict[str, float] = {}
        self.layout_offsets: dict[str, float] = {}
        self.closing_tabs: set[str] = set()
        self.animations: dict[str, QVariantAnimation] = {}
        self.drag_layout_snapshot: dict[str, QRect] = {}
        self.drag_active = False
        self.native_drag_started = False
        self.drag_offset = QPoint()
        self.pressed_tab_id: str | None = None
        self.pressed_tab_index = -1
        self.tab_drag_start_pos = QPoint()
        self.tab_drag_native_move_attempted = False
        self.tab_drag_promoted_to_window_move = False
        self.tab_drag_reorder_suspended = False
        self.loading_tabs: set[str] = set()
        self.spinner_angle = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.setInterval(24)
        self.spinner_timer.timeout.connect(self._advance_spinner)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setUsesScrollButtons(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        font = QFont(self.font())
        font.setPointSize(self.TAB_FONT_SIZE)
        font.setWeight(500)
        self.setFont(font)
        self.currentChanged.connect(lambda _index: self._sync_visual_states())

    def tabSizeHint(self, index: int) -> QSize:
        metrics = self.fontMetrics()
        text = self.tabText(index)
        width = (
            self.TAB_HORIZONTAL_PADDING
            + metrics.horizontalAdvance(text)
            + self.TAB_TEXT_ICON_GAP
            + self.TAB_CLOSE_ICON_SIZE
            + self.TAB_HORIZONTAL_PADDING
        )
        width = max(self.TAB_MIN_WIDTH, min(width, self.TAB_MAX_WIDTH))
        return QSize(width, TITLEBAR_HEIGHT)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        metrics = self.fontMetrics()
        stroke_color = QColor("#444444")
        painter.fillRect(self.rect(), QColor("#2C2C2A"))

        for index in range(self.count()):
            tab_id = self._tab_id(index)
            if not tab_id:
                continue
            rect = self._animated_tab_rect(index)
            if not rect.isValid() or rect.width() < 6:
                continue

            painter.save()
            painter.setClipRect(rect)
            active = index == self.currentIndex()
            hover_progress = self.tab_hover_progress.get(tab_id, 0.0)
            fill_alpha = self.ACTIVE_FILL_ALPHA if active else self.HOVER_FILL_ALPHA * hover_progress
            tab_rect = rect.adjusted(0.0, 0.0, -1.0, -1.0)
            fill_color = QColor(0, 0, 0)
            fill_color.setAlphaF(fill_alpha)
            painter.fillRect(tab_rect, fill_color)
            painter.setPen(QPen(stroke_color, 1))
            top_left_x = tab_rect.left() + (1.0 if index == 0 else 0.0)
            painter.drawLine(QPointF(top_left_x, tab_rect.top()), QPointF(tab_rect.right(), tab_rect.top()))
            painter.drawLine(QPointF(top_left_x, tab_rect.bottom()), QPointF(tab_rect.right(), tab_rect.bottom()))
            painter.drawLine(QPointF(tab_rect.right(), tab_rect.top()), QPointF(tab_rect.right(), tab_rect.bottom()))

            text_rect = self._tab_text_rect(rect, tab_id)
            if tab_id in self.loading_tabs:
                self._paint_spinner(painter, self._spinner_rect(rect))
            text = metrics.elidedText(self.tabText(index), self.elideMode(), max(0, int(text_rect.width())))
            text_color = QColor(255, 255, 255, 255 if active else round(255 * 0.7))
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

            close_rect = self._close_icon_rect(rect)
            close_circle_alpha = self.close_circle_progress.get(tab_id, 0.0)
            if close_circle_alpha > 0.001:
                circle_color = QColor(0, 0, 0)
                circle_color.setAlphaF(close_circle_alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(circle_color)
                painter.drawEllipse(close_rect.adjusted(-4, -4, 4, 4))
            close_opacity = self.close_icon_progress.get(tab_id, 0.0) * self.ICON_ALPHA
            if close_opacity > 0.001:
                painter.save()
                painter.setOpacity(close_opacity)
                self.close_icon_renderer.render(painter, QRectF(close_rect))
                painter.restore()
            painter.restore()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            close_tab_id = self._tab_id_at_close_icon(event.position().toPoint())
            if close_tab_id:
                self._reset_tab_drag_state()
                self.pressed_close_tab_id = close_tab_id
                self._sync_visual_states()
                event.accept()
                return
            pressed_index = self.tabAt(event.position().toPoint())
            if pressed_index >= 0:
                self.drag_layout_snapshot = self.capture_layout()
                self.pressed_tab_index = pressed_index
                self.pressed_tab_id = self._tab_id(pressed_index)
                self.tab_drag_start_pos = event.position().toPoint()
                self.tab_drag_native_move_attempted = False
                self.tab_drag_promoted_to_window_move = False
            else:
                self._reset_tab_drag_state()
            if pressed_index < 0:
                if not self._start_window_drag(event):
                    self.drag_active = True
                    self.native_drag_started = False
                    self.drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
                    self.grabMouse()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_active:
            self.releaseMouse()
        self.drag_active = False
        self.native_drag_started = False
        if self.pressed_close_tab_id and event.button() == Qt.MouseButton.LeftButton:
            close_tab_id = self._tab_id_at_close_icon(event.position().toPoint())
            pressed_tab_id = self.pressed_close_tab_id
            self.pressed_close_tab_id = None
            self._sync_visual_states()
            if close_tab_id == pressed_tab_id:
                index = self._index_for_tab_id(close_tab_id)
                if index >= 0:
                    self.tabCloseRequested.emit(index)
                event.accept()
                return
        self.pressed_close_tab_id = None
        self._sync_visual_states()
        self._reset_tab_drag_state()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._tab_id_at_close_icon(event.position().toPoint()):
            self.window().toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_active and not self.window().isMaximized():
            if not self.native_drag_started and self._start_window_drag(event):
                self.native_drag_started = True
                self.releaseMouse()
                self.drag_active = False
                event.accept()
                return
            self.window().move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        if self._should_promote_tab_drag(event):
            self.tab_drag_native_move_attempted = True
            if self._start_tab_drag_window_move(event):
                event.accept()
                return
        if self.tab_drag_promoted_to_window_move:
            event.accept()
            return
        hovered_index = self.tabAt(event.position().toPoint())
        self.hovered_tab_id = self._tab_id(hovered_index) if hovered_index >= 0 else None
        self.hovered_close_tab_id = self._tab_id_at_close_icon(event.position().toPoint())
        self._sync_visual_states()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered_tab_id = None
        self.hovered_close_tab_id = None
        self.pressed_close_tab_id = None
        self._sync_visual_states()
        super().leaveEvent(event)

    def capture_layout(self) -> dict[str, QRect]:
        layout: dict[str, QRect] = {}
        for index in range(self.count()):
            tab_id = self._tab_id(index)
            if tab_id:
                layout[tab_id] = self.tabRect(index)
        return layout

    def animate_layout_change(self, previous_layout: dict[str, QRect]) -> None:
        for index in range(self.count()):
            tab_id = self._tab_id(index)
            if not tab_id:
                continue
            current_rect = self.tabRect(index)
            previous_rect = previous_layout.get(tab_id)
            if previous_rect is None:
                continue
            offset = float(previous_rect.x() - current_rect.x())
            self.layout_offsets[tab_id] = offset
            self._animate_dict_value("layout", self.layout_offsets, tab_id, 0.0, duration=self.ANIMATION_MS)

    def take_drag_layout_snapshot(self) -> dict[str, QRect]:
        snapshot = self.drag_layout_snapshot
        self.drag_layout_snapshot = {}
        return snapshot

    def animate_open_tab(self, tab_id: str) -> None:
        self.open_progress[tab_id] = 0.0
        self._animate_dict_value("open", self.open_progress, tab_id, 1.0, duration=self.ANIMATION_MS)
        self._sync_visual_states()

    def animate_close_tab(self, tab_id: str, on_finished) -> bool:
        if tab_id in self.closing_tabs:
            return True
        if self._index_for_tab_id(tab_id) < 0:
            return False
        self.closing_tabs.add(tab_id)
        self.close_progress[tab_id] = 1.0
        self._animate_dict_value(
            "close",
            self.close_progress,
            tab_id,
            0.0,
            duration=self.ANIMATION_MS,
            finished=lambda: self._finish_close_animation(tab_id, on_finished),
        )
        return True

    def _finish_close_animation(self, tab_id: str, on_finished) -> None:
        self.closing_tabs.discard(tab_id)
        self.close_progress.pop(tab_id, None)
        self.close_icon_progress.pop(tab_id, None)
        self.close_circle_progress.pop(tab_id, None)
        self.tab_hover_progress.pop(tab_id, None)
        self.layout_offsets.pop(tab_id, None)
        on_finished()

    def _start_window_drag(self, event) -> bool:
        del event
        window = self.window()
        if hasattr(window, "start_system_move") and window.start_system_move():
            return True
        if window.isMaximized():
            return False
        return False

    def _start_tab_drag_window_move(self, event) -> bool:
        if not self._start_window_drag(event):
            return False
        if not self.tab_drag_reorder_suspended:
            self.setMovable(False)
            self.tab_drag_reorder_suspended = True
        self.tab_drag_promoted_to_window_move = True
        return True

    def _reset_tab_drag_state(self) -> None:
        self.pressed_tab_id = None
        self.pressed_tab_index = -1
        self.tab_drag_start_pos = QPoint()
        self.tab_drag_native_move_attempted = False
        self.tab_drag_promoted_to_window_move = False
        if self.tab_drag_reorder_suspended:
            self.setMovable(True)
            self.tab_drag_reorder_suspended = False

    def _should_promote_tab_drag(self, event) -> bool:
        if self.pressed_tab_index < 0 or not self.pressed_tab_id:
            return False
        current_index = self._index_for_tab_id(self.pressed_tab_id)
        if current_index < 0:
            return False
        self.pressed_tab_index = current_index
        if self.tab_drag_native_move_attempted or self.tab_drag_promoted_to_window_move:
            return False
        if self.pressed_close_tab_id:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        point = event.position().toPoint()
        if (point - self.tab_drag_start_pos).manhattanLength() < self._drag_threshold():
            return False
        return self._is_outside_reorder_band(point)

    def _is_outside_reorder_band(self, point: QPoint) -> bool:
        padding = self._drag_threshold() + self.REORDER_BAND_PADDING
        return point.y() < -padding or point.y() > self.height() + padding

    def _drag_threshold(self) -> int:
        app = QApplication.instance()
        return app.startDragDistance() if app is not None else 10

    def _animated_tab_rect(self, index: int) -> QRectF:
        rect = QRectF(self.tabRect(index))
        tab_id = self._tab_id(index)
        if not tab_id:
            return rect
        rect.translate(self.layout_offsets.get(tab_id, 0.0), 0.0)
        if tab_id in self.closing_tabs:
            progress = self.close_progress.get(tab_id, 1.0)
            rect.setWidth(rect.width() * progress)
            return rect
        progress = self.open_progress.get(tab_id, 1.0)
        if progress < 1.0:
            rect.setWidth(rect.width() * progress)
        return rect

    def _spinner_rect(self, rect: QRectF) -> QRectF:
        left = rect.left() + self.TAB_HORIZONTAL_PADDING
        top = rect.top() + (rect.height() - self.SPINNER_SIZE) / 2
        return QRectF(left, top, self.SPINNER_SIZE, self.SPINNER_SIZE)

    def _tab_text_rect(self, rect: QRectF, tab_id: str) -> QRectF:
        left = rect.left() + self.TAB_HORIZONTAL_PADDING
        if tab_id in self.loading_tabs:
            left += self.SPINNER_SIZE + self.SPINNER_GAP
        right = rect.right() - self.TAB_HORIZONTAL_PADDING - self.TAB_CLOSE_ICON_SIZE - self.TAB_TEXT_ICON_GAP
        return QRectF(left, rect.top(), max(0.0, right - left), rect.height())

    def _close_icon_rect(self, rect: QRectF) -> QRectF:
        x = rect.right() - self.TAB_HORIZONTAL_PADDING - self.TAB_CLOSE_ICON_SIZE
        y = rect.top() + (rect.height() - self.TAB_CLOSE_ICON_SIZE) / 2
        return QRectF(x, y, self.TAB_CLOSE_ICON_SIZE, self.TAB_CLOSE_ICON_SIZE)

    def _tab_id(self, index: int) -> str | None:
        if index < 0 or index >= self.count():
            return None
        tab_id = self.tabData(index)
        return tab_id if isinstance(tab_id, str) else None

    def _index_for_tab_id(self, tab_id: str | None) -> int:
        if not tab_id:
            return -1
        for index in range(self.count()):
            if self._tab_id(index) == tab_id:
                return index
        return -1

    def _tab_id_at_close_icon(self, point: QPoint) -> str | None:
        for index in range(self.count()):
            tab_id = self._tab_id(index)
            if not tab_id or self.close_icon_progress.get(tab_id, 0.0) <= 0.02:
                continue
            rect = self._close_icon_rect(self._animated_tab_rect(index)).adjusted(-6, -6, 6, 6)
            if rect.contains(QPointF(point)):
                return tab_id
        return None

    def _sync_visual_states(self) -> None:
        for index in range(self.count()):
            tab_id = self._tab_id(index)
            if not tab_id:
                continue
            active = index == self.currentIndex()
            hover_target = 1.0 if self.hovered_tab_id == tab_id and not active else 0.0
            close_target = 1.0 if active or self.hovered_tab_id == tab_id else 0.0
            circle_target = 0.0
            if self.pressed_close_tab_id == tab_id:
                circle_target = self.CLOSE_PRESSED_CIRCLE_ALPHA
            elif self.hovered_close_tab_id == tab_id:
                circle_target = self.CLOSE_HOVER_CIRCLE_ALPHA
            self._animate_dict_value("hover", self.tab_hover_progress, tab_id, hover_target)
            self._animate_dict_value("close_icon", self.close_icon_progress, tab_id, close_target)
            self._animate_dict_value("close_circle", self.close_circle_progress, tab_id, circle_target)
        self.update()

    def set_tab_loading(self, tab_id: str, is_loading: bool) -> None:
        if is_loading:
            self.loading_tabs.add(tab_id)
        else:
            self.loading_tabs.discard(tab_id)
        if self.loading_tabs:
            if not self.spinner_timer.isActive():
                self.spinner_timer.start()
        else:
            self.spinner_timer.stop()
        self.update()

    def _advance_spinner(self) -> None:
        self.spinner_angle = (self.spinner_angle + 24) % 360
        self.update()

    def _paint_spinner(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(QColor(255, 255, 255, round(255 * 0.7)))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = 1.0
        spinner_rect = rect.adjusted(inset, inset, -inset, -inset)
        painter.drawArc(spinner_rect, -self.spinner_angle * 16, 250 * 16)

    def _animate_dict_value(
        self,
        group: str,
        store: dict[str, float],
        tab_id: str,
        target: float,
        *,
        duration: int = ANIMATION_MS,
        finished=None,
    ) -> None:
        key = f"{group}:{tab_id}"
        current = store.get(tab_id, 0.0)
        if abs(current - target) < 0.001:
            return
        animation = self.animations.get(key)
        if animation is None:
            animation = QVariantAnimation(self)
            animation.valueChanged.connect(lambda value, data=store, item=tab_id: self._set_store_value(data, item, value))
            self.animations[key] = animation
        else:
            try:
                animation.finished.disconnect()
            except TypeError:
                pass
        animation.stop()
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(current)
        animation.setEndValue(target)
        if finished is not None:
            animation.finished.connect(finished)
        animation.start()

    def _set_store_value(self, store: dict[str, float], tab_id: str, value) -> None:
        store[tab_id] = float(value)
        self.update()


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self.drag_active = False
        self.native_drag_started = False
        self.drag_offset = QPoint()
        self.setFixedHeight(TITLEBAR_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tab_bar = TitleTabBar(self)
        self.tab_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.tab_bar)

        self.add_button = SvgIconButton(
            ASSETS_DIR / "titlebar-plus.svg",
            "New tab",
            self,
            icon_size=16,
            button_size=QSize(32, 32),
            icon_opacity=0.7,
            circle_base_alpha=0.0,
            circle_hover_alpha=0.24,
            circle_pressed_alpha=0.64,
        )
        self.add_button.setObjectName("addTabButton")
        layout.addWidget(self.add_button)
        layout.addStretch(1)

        self.close_button = SvgIconButton(
            ASSETS_DIR / "titlebar-close.svg",
            "Close",
            self,
            icon_size=14,
            button_size=QSize(32, 32),
            icon_opacity=0.7,
            circle_base_alpha=0.24,
            circle_hover_alpha=0.40,
            circle_pressed_alpha=0.64,
        )
        self.close_button.setObjectName("closeButton")
        layout.addWidget(self.close_button)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#2C2C2A"))
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    def mousePressEvent(self, event) -> None:
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and child not in {self.add_button, self.close_button}:
            if not self.window.start_system_move():
                self.drag_active = True
                self.native_drag_started = False
                self.drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
                self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_active and not self.window.isMaximized():
            if not self.native_drag_started:
                if self.window.start_system_move():
                    self.native_drag_started = True
                    self.releaseMouse()
                    self.drag_active = False
                    event.accept()
                    return
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_active:
            self.releaseMouse()
        self.drag_active = False
        self.native_drag_started = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and child not in {self.add_button, self.close_button}:
            self.window.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeGrip(QWidget):
    def __init__(self, window: "MainWindow", edges, cursor: Qt.CursorShape):
        super().__init__(window)
        self.main_window = window
        self.edges = edges
        self.drag_active = False
        self.drag_origin = QPoint()
        self.start_geometry = QRect()
        self.setCursor(cursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not (self.main_window.isMaximized() or self.main_window.isFullScreen()):
            self.drag_origin = event.globalPosition().toPoint()
            self.start_geometry = self.main_window.geometry()
            if not self.main_window.start_system_resize(self.edges):
                self.drag_active = True
                self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_active:
            delta = event.globalPosition().toPoint() - self.drag_origin
            self.main_window.apply_manual_resize(self.edges, self.start_geometry, delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_active and event.button() == Qt.MouseButton.LeftButton:
            self.releaseMouse()
            self.drag_active = False
            event.accept()
            return
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
    RESIZE_MARGIN = 6
    CORNER_GRIP_SIZE = 12

    def __init__(self, logger, font_helper, updater):
        super().__init__()
        self.logger = logger
        self.font_helper = font_helper
        self.updater = updater
        self._last_paste_shortcut_override_at = 0.0
        self._last_paste_shortcut_override_view_id: int | None = None
        self.profile = self._build_profile()
        self.tab_counter = itertools.count(1)
        self.tabs: dict[str, TabState] = {}
        self.tab_order: list[str] = []
        self.active_downloads: dict[int, QWebEngineDownloadRequest] = {}
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
        self._resize_grips = self._create_resize_grips()

        self.toast = ToastOverlay(self)
        self._apply_styles()
        self._wire_window_controls()
        self._wire_tab_strip()
        self._install_shortcuts()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.updater.updateReady.connect(self._on_update_ready)
        self.restore_session()
        self._update_resize_grips()

    def _build_profile(self) -> QWebEngineProfile:
        base_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        profile_root = base_dir / "web-profile"
        profile = QWebEngineProfile(APP_ID, self)
        configure_profile(profile, profile_root, self.logger)
        profile.downloadRequested.connect(self._on_download_requested)
        return profile

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
              background: #11151b;
              color: #eef2f8;
            }
            TitleBar {
              background: #2c2c2a;
              border-bottom: 1px solid #444444;
            }
            QTabBar {
              background: #2c2c2a;
            }
            QTabBar::tab {
              background: transparent;
              border: none;
              margin: 0;
              padding: 0;
              color: transparent;
            }
            QPushButton {
              background: transparent;
              color: #eff5ff;
              border: none;
            }
            QPushButton:hover {
              background: transparent;
            }
            #addTabButton {
              margin-right: 0px;
            }
            #closeButton {
              margin-left: 4px;
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
            ("Ctrl+Q", self.close),
            ("Meta+Q", self.close),
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

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        QTimer.singleShot(0, self._update_resize_grips)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_resize_grips()
        if self.toast.isVisible():
            width = min(380, self.width() - 24)
            self.toast.setGeometry(QRect(self.width() - width - 16, TITLEBAR_HEIGHT + 14, width, self.toast.height() or 90))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._update_resize_grips)

    def eventFilter(self, watched, event) -> bool:
        if event.type() not in {QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress}:
            return super().eventFilter(watched, event)
        if not self._is_paste_key_event(event):
            return super().eventFilter(watched, event)
        view = self._focused_managed_figmux_view(watched)
        if view is None:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.ShortcutOverride and self._skip_duplicate_paste_shortcut_override(view):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.KeyPress and self._skip_duplicate_paste_keypress(view):
            return super().eventFilter(watched, event)

        trigger_event = "shortcut_override" if event.type() == QEvent.Type.ShortcutOverride else "key_press"
        normalize_clipboard_image_for_paste(view.page(), trigger_event=trigger_event)
        if event.type() == QEvent.Type.ShortcutOverride:
            self._last_paste_shortcut_override_at = time.monotonic()
            self._last_paste_shortcut_override_view_id = id(view)
        return super().eventFilter(watched, event)

    def _is_paste_key_event(self, event) -> bool:
        matches = getattr(event, "matches", None)
        return bool(callable(matches) and matches(QKeySequence.StandardKey.Paste))

    def _focused_managed_figmux_view(self, watched) -> FigmuxWebView | None:
        candidates: list[QWidget] = []
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QWidget):
            candidates.append(focus_widget)
        if isinstance(watched, QWidget) and watched not in candidates:
            candidates.append(watched)

        for widget in candidates:
            current = widget
            while current is not None:
                if isinstance(current, FigmuxWebView) and self._is_managed_figmux_view(current):
                    return current
                current = current.parentWidget()
        return None

    def _is_managed_figmux_view(self, view: FigmuxWebView) -> bool:
        window = view.window()
        return window is self or any(popup is window for popup in self.popup_windows)

    def _skip_duplicate_paste_keypress(self, view: FigmuxWebView) -> bool:
        if self._last_paste_shortcut_override_view_id != id(view):
            return False
        return (time.monotonic() - self._last_paste_shortcut_override_at) < 0.4

    def _skip_duplicate_paste_shortcut_override(self, view: FigmuxWebView) -> bool:
        if self._last_paste_shortcut_override_view_id != id(view):
            return False
        return (time.monotonic() - self._last_paste_shortcut_override_at) < 0.15

    def _create_resize_grips(self) -> dict[str, ResizeGrip]:
        return {
            "top_left": ResizeGrip(self, Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeFDiagCursor),
            "top": ResizeGrip(self, Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            "top_right": ResizeGrip(self, Qt.Edge.TopEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeBDiagCursor),
            "left": ResizeGrip(self, Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            "right": ResizeGrip(self, Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            "bottom_left": ResizeGrip(self, Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeBDiagCursor),
            "bottom": ResizeGrip(self, Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            "bottom_right": ResizeGrip(self, Qt.Edge.BottomEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeFDiagCursor),
        }

    def _update_resize_grips(self) -> None:
        if not self._resize_grips:
            return
        enabled = not (self.isMaximized() or self.isFullScreen())
        for grip in self._resize_grips.values():
            grip.setVisible(enabled)
        if not enabled:
            return

        margin = self.RESIZE_MARGIN
        corner = self.CORNER_GRIP_SIZE
        width = self.width()
        height = self.height()
        top_span = max(0, width - (2 * corner))
        side_span = max(0, height - (2 * corner))

        self._resize_grips["top_left"].setGeometry(0, 0, corner, corner)
        self._resize_grips["top"].setGeometry(corner, 0, top_span, margin)
        self._resize_grips["top_right"].setGeometry(width - corner, 0, corner, corner)
        self._resize_grips["left"].setGeometry(0, corner, margin, side_span)
        self._resize_grips["right"].setGeometry(width - margin, corner, margin, side_span)
        self._resize_grips["bottom_left"].setGeometry(0, height - corner, corner, corner)
        self._resize_grips["bottom"].setGeometry(corner, height - margin, top_span, margin)
        self._resize_grips["bottom_right"].setGeometry(width - corner, height - corner, corner, corner)

        for grip in self._resize_grips.values():
            grip.raise_()

    def start_system_resize(self, edges) -> bool:
        if self.isMaximized() or self.isFullScreen():
            return False
        handle = self.windowHandle()
        return bool(handle is not None and handle.startSystemResize(edges))

    def start_system_move(self) -> bool:
        if self.isMaximized() or self.isFullScreen():
            return False
        handle = self.windowHandle()
        return bool(handle is not None and handle.startSystemMove())

    def apply_manual_resize(self, edges, start_geometry: QRect, delta: QPoint) -> None:
        left = start_geometry.left()
        right = start_geometry.right()
        top = start_geometry.top()
        bottom = start_geometry.bottom()
        minimum_width = max(1, self.minimumWidth())
        minimum_height = max(1, self.minimumHeight())

        if edges & Qt.Edge.LeftEdge:
            left = min(left + delta.x(), right - minimum_width + 1)
        if edges & Qt.Edge.RightEdge:
            right = max(right + delta.x(), left + minimum_width - 1)
        if edges & Qt.Edge.TopEdge:
            top = min(top + delta.y(), bottom - minimum_height + 1)
        if edges & Qt.Edge.BottomEdge:
            bottom = max(bottom + delta.y(), top + minimum_height - 1)

        self.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))

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
        bar = self.title_bar.tab_bar
        tab_id = self._next_tab_id()
        tab = self._build_tab(tab_id, url, title)
        if insert_index is None:
            insert_index = len(self.tab_order)
        insert_index = max(0, min(insert_index, len(self.tab_order)))
        self.tabs[tab_id] = tab
        self.tab_order.insert(insert_index, tab_id)
        self.stack.insertWidget(insert_index, tab.view)
        bar.insertTab(insert_index, title)
        bar.setTabData(insert_index, tab_id)
        bar.setTabToolTip(insert_index, url)
        bar.animate_open_tab(tab_id)
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
        if self.shutting_down:
            self._finalize_closed_tab(tab_id, remember=True)
            return
        if not self.title_bar.tab_bar.animate_close_tab(tab_id, lambda tid=tab_id: self._finalize_closed_tab(tid, remember=True)):
            self._finalize_closed_tab(tab_id, remember=True)

    def _finalize_closed_tab(self, tab_id: str, remember: bool) -> None:
        if tab_id not in self.tabs or tab_id not in self.tab_order:
            return
        index = self.tab_order.index(tab_id)
        tab = self.tabs.pop(tab_id)
        self.tab_order.pop(index)
        self.title_bar.tab_bar.set_tab_loading(tab_id, False)
        if remember:
            self.closed_tabs.append((tab.url, tab.title, index))
        self.title_bar.tab_bar.removeTab(index)
        self.stack.removeWidget(tab.view)
        tab.page.deleteLater()
        tab.view.deleteLater()
        log_event(self.logger, "tab_closed", tab_id=tab_id, index=index, url=tab.url)
        if not self.tab_order and not self.shutting_down:
            self.create_tab()
        elif self.tab_order:
            next_index = min(self.title_bar.tab_bar.currentIndex(), len(self.tab_order) - 1)
            self.activate_tab(self.tab_order[max(next_index, 0)])
        self.queue_persist_session()

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
        previous_layout = self.title_bar.tab_bar.take_drag_layout_snapshot()
        tab_id = self.tab_order.pop(from_index)
        self.tab_order.insert(to_index, tab_id)
        widget = self.stack.widget(from_index)
        self.stack.removeWidget(widget)
        self.stack.insertWidget(to_index, widget)
        for index, item_tab_id in enumerate(self.tab_order):
            self.title_bar.tab_bar.setTabData(index, item_tab_id)
        if previous_layout:
            self.title_bar.tab_bar.animate_layout_change(previous_layout)
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
        reload_tab = QAction("Reload Tab", self)
        reload_tab.triggered.connect(lambda: self.reload_tab(tab_id))
        close = QAction("Close Tab", self)
        close.triggered.connect(lambda: self.close_tab(tab_id))
        menu.addAction(reopen)
        menu.addAction(reload_tab)
        menu.addAction(close)
        menu.exec(self.title_bar.tab_bar.mapToGlobal(point))

    def reload_tab(self, tab_id: str) -> None:
        if tab_id not in self.tabs:
            return
        self.tabs[tab_id].page.triggerAction(self.tabs[tab_id].page.WebAction.Reload)
        self.activate_tab(tab_id)

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
        self.title_bar.tab_bar.set_tab_loading(tab_id, True)
        log_event(self.logger, "tab_load_started", tab_id=tab_id, url=self.tabs[tab_id].url)

    def _on_tab_load_finished(self, tab_id: str, ok: bool) -> None:
        if tab_id not in self.tabs:
            return
        tab = self.tabs[tab_id]
        tab.is_loading = False
        self.title_bar.tab_bar.set_tab_loading(tab_id, False)
        tab.can_go_back = tab.page.history().canGoBack()
        tab.can_go_forward = tab.page.history().canGoForward()
        tab.page.inject_input_debug()
        tab.page.inject_cursor_debug()
        self._log_cursor_debug(tab)
        log_event(self.logger, "tab_load_finished", tab_id=tab_id, ok=ok, url=tab.url)

    def _log_cursor_debug(self, tab: TabState) -> None:
        if os.environ.get("FIGMUX_CURSOR_DEBUG") != "1":
            return
        view = tab.view
        window = view.window()
        window_handle = window.windowHandle() if window else None
        screen = view.screen() or QApplication.primaryScreen()
        log_event(
            self.logger,
            "cursor_debug_qt",
            tab_id=tab.id,
            url=tab.url,
            window_device_pixel_ratio=float(window_handle.devicePixelRatio()) if window_handle else None,
            screen_name=screen.name() if screen else None,
            screen_device_pixel_ratio=float(screen.devicePixelRatio()) if screen else None,
            screen_logical_dpi_x=float(screen.logicalDotsPerInchX()) if screen else None,
            screen_logical_dpi_y=float(screen.logicalDotsPerInchY()) if screen else None,
            screen_physical_dpi_x=float(screen.physicalDotsPerInchX()) if screen else None,
            screen_physical_dpi_y=float(screen.physicalDotsPerInchY()) if screen else None,
            view_width=view.width(),
            view_height=view.height(),
            env={
                name: os.environ.get(name)
                for name in (
                    "DISPLAY",
                    "WAYLAND_DISPLAY",
                    "XCURSOR_SIZE",
                    "QT_AUTO_SCREEN_SCALE_FACTOR",
                    "QT_ENABLE_HIGHDPI_SCALING",
                    "QT_FONT_DPI",
                    "QT_QPA_PLATFORM",
                    "QT_QPA_PLATFORMTHEME",
                    "QT_SCALE_FACTOR",
                    "QT_SCALE_FACTOR_ROUNDING_POLICY",
                    "QT_SCREEN_SCALE_FACTORS",
                    "QTWEBENGINE_CHROMIUM_FLAGS",
                )
                if os.environ.get(name) is not None
            },
        )

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

    def _default_download_path(self, download: QWebEngineDownloadRequest) -> Path:
        downloads_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        base_dir = Path(downloads_dir) if downloads_dir else Path.home() / "Downloads"
        filename = (download.downloadFileName() or "").strip() or "download"
        return base_dir / filename

    def _on_download_requested(self, download: QWebEngineDownloadRequest) -> None:
        target_path = self._default_download_path(download)
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save as",
            str(target_path),
        )
        if not selected_path:
            download.cancel()
            log_event(
                self.logger,
                "download_cancelled_before_start",
                suggested_path=str(target_path),
                url=download.url().toString(),
            )
            return

        destination = Path(selected_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        download.setDownloadDirectory(str(destination.parent))
        download.setDownloadFileName(destination.name)
        download.stateChanged.connect(lambda _state, request=download: self._on_download_state_changed(request))
        self.active_downloads[id(download)] = download
        download.accept()
        self.show_toast("Download started", destination.name, duration_ms=3200)
        log_event(
            self.logger,
            "download_started",
            path=str(destination),
            url=download.url().toString(),
            mime_type=download.mimeType(),
        )

    def _on_download_state_changed(self, download: QWebEngineDownloadRequest) -> None:
        state = download.state()
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            path = str(Path(download.downloadDirectory()) / download.downloadFileName())
            self.show_toast("Download complete", download.downloadFileName())
            log_event(self.logger, "download_completed", path=path, url=download.url().toString())
            self.active_downloads.pop(id(download), None)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            reason = download.interruptReasonString() or "Download failed."
            self.show_toast("Download failed", reason)
            log_event(
                self.logger,
                "download_interrupted",
                reason=reason,
                url=download.url().toString(),
            )
            self.active_downloads.pop(id(download), None)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            log_event(
                self.logger,
                "download_cancelled",
                filename=download.downloadFileName(),
                url=download.url().toString(),
            )
            self.active_downloads.pop(id(download), None)

    def _handle_input_debug(self, payload: dict) -> None:
        normalized_payload = dict(payload)
        console_message = normalized_payload.pop("message", None)
        if console_message is not None:
            normalized_payload["console_message"] = console_message
        log_event(self.logger, "input_debug", **normalized_payload)

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
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.persist_session()
        self.updater.install_on_exit(relaunch=self._relaunch_after_update)
        for popup in list(self.popup_windows):
            popup.close()
        for tab_id in list(self.tab_order):
            if tab_id in self.tabs:
                self._finalize_closed_tab(tab_id, remember=False)
        self.font_helper.stop()
        super().closeEvent(event)
