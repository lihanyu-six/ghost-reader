# -*- coding: utf-8 -*-
"""幽灵阅读器 —— 入口。"""
import os
import sys
import ctypes

# 高 DPI（必须在 QApplication 之前）
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_window import GhostReader, APP_NAME  # noqa: E402


def main():
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ghost.reader.1")
        except Exception:
            pass

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei", 9))

    book = ""
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        candidate = args[0]
        if os.path.exists(candidate):
            book = candidate

    win = GhostReader(book)
    if not win.cfg.get("always_on_top") is False:
        pass
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
