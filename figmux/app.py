from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from figmux.app_logging import configure_logging
from figmux.constants import APP_ID, APP_NAME, ASSETS_DIR, ORGANIZATION_DOMAIN, ORGANIZATION_NAME, PROJECT_ROOT
from figmux.font_helper import FontHelperService
from figmux.main_window import MainWindow
from figmux.updater import AppImageUpdater


def build_application() -> QApplication:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORGANIZATION_NAME)
    QApplication.setOrganizationDomain(ORGANIZATION_DOMAIN)
    app = QApplication(sys.argv)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(True)
    icon_path = ASSETS_DIR / "com.figmux.app.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    return app


def run() -> int:
    logger = configure_logging()
    app = build_application()
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    font_helper = FontHelperService(logger, PROJECT_ROOT)
    font_helper.start()
    updater = AppImageUpdater(logger, app)
    window = MainWindow(logger, font_helper, updater)
    window.show()
    updater.start()
    return app.exec()
