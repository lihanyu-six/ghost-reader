# -*- coding: utf-8 -*-
"""无边框 / 拉伸 / 投屏隐藏 / 老板键 / 快捷键 等窗口能力。"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QEvent
from PySide6.QtWidgets import QWidget

IS_WIN = sys.platform.startswith("win")

# ------------------------------------------------------------- 全局热键

if IS_WIN:
    import ctypes.wintypes as wt

    class _MSG(ctypes.Structure):
        _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT), ("wParam", wt.WPARAM),
                    ("lParam", wt.LPARAM), ("time", wt.DWORD), ("pt", wt.POINT)]

    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY = 0x0312
    user32 = ctypes.windll.user32


class GlobalHotkey(QObject):
    """Windows 全局热键。基于 QAbstractNativeEventFilter 监听 WM_HOTKEY。"""

    triggered = Signal(str)

    _registry: list = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = {}
        self._next_id = 0xC100
        self._filter = None

    def register(self, name: str, vk: int, modifiers: int) -> bool:
        if not IS_WIN:
            return False
        self._next_id += 1
        hid = self._next_id
        mods = modifiers | MOD_NOREPEAT
        if not user32.RegisterHotKey(None, hid, mods, vk):
            return False
        self._ids[hid] = name
        GlobalHotkey._registry.append((self, hid))
        return True

    def ensure_filter(self, app):
        if self._filter is not None or not IS_WIN:
            return

        outer = self

        class _Filter(QObject):
            def eventFilter(self, obj, event):  # noqa: N802
                et = event.type()
                if et == QEvent.Type.NativeEvent if hasattr(QEvent, "Type") else False:
                    pass
                return False

        # 直接使用原生事件过滤器（PySide6 提供 QAbstractNativeEventFilter）
        from PySide6.QtCore import QAbstractNativeEventFilter

        class _NativeFilter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, eventType, message):  # noqa: N802
                if eventType == b"windows_generic_MSG" or eventType == "windows_generic_MSG":
                    msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                    if msg.message == WM_HOTKEY:
                        for inst, hid in list(GlobalHotkey._registry):
                            if hid == msg.wParam:
                                inst.triggered.emit(inst._ids.get(hid, ""))
                                return False, 0
                return False, 0

        self._filter = _NativeFilter()
        app.installNativeEventFilter(self._filter)

    def dispose(self):
        if not IS_WIN:
            return
        for hid in list(self._ids.keys()):
            try:
                user32.UnregisterHotKey(None, hid)
            except Exception:
                pass
            GlobalHotkey._registry = [(i, h) for (i, h) in GlobalHotkey._registry if h != hid]
        self._ids.clear()


# 常用虚拟键码
VK = {
    "`": 0xC0, "~": 0xC0, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
    "Q": 0x51, "W": 0x57, "E": 0x45, "R": 0x52, "T": 0x54, "Y": 0x59,
    "U": 0x55, "I": 0x49, "O": 0x4F, "P": 0x50, "A": 0x41, "S": 0x53,
    "D": 0x44, "F": 0x46, "G": 0x47, "H": 0x48, "J": 0x4A, "K": 0x4B,
    "L": 0x4C, "Z": 0x5A, "X": 0x58, "C": 0x43, "V": 0x56, "B": 0x42,
    "N": 0x4E, "M": 0x4D,
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "F1": 0x70, "F2": 0x71,
    "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75, "F7": 0x76,
    "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}

HOTKEY_PRESETS = [
    ("Ctrl + `", 0xC0, MOD_CONTROL),
    ("Ctrl + Shift + `", 0xC0, MOD_CONTROL | MOD_SHIFT),
    ("Ctrl + Alt + `", 0xC0, MOD_CONTROL | MOD_ALT),
    ("Ctrl + F12", 0x7B, MOD_CONTROL),
    ("Ctrl + Alt + Q", 0x51, MOD_CONTROL | MOD_ALT),
    ("Ctrl + Shift + Space", 0x20, MOD_CONTROL | MOD_SHIFT),
]


# ------------------------------------------------------------- 投屏检测

def detect_capture() -> bool:
    """粗略检测当前是否有录屏/投屏程序在运行。"""
    if not IS_WIN:
        return False
    import subprocess
    keywords = [
        "obs64", "obs32", "obs ", "fsrecorder", "screenrecorder", "sunlogin",
        "todesk", "anydesk", "teamviewer", "vnc", "airdroid", "scrcpy",
        "douyin", "kuaishou", "obs-studio", "bandicam", "camtasia", "xsplit",
    ]
    try:
        raw = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout or b""
    except Exception:
        return False
    # 中文 Windows 的 tasklist 输出是 GBK，用 text=True 会抛 UnicodeDecodeError
    # 导致检测静默失效。这里统一按字节解码，只匹配 ASCII 关键词，乱码无影响。
    out = raw.decode("utf-8", errors="replace").lower()
    return any(k in out for k in keywords)


# ------------------------------------------------------------- 可拉伸无边框窗口

class FramelessWindow(QWidget):
    """支持边缘拖拽缩放的无边框窗口。

    缩放逻辑抽成 _resize_begin/_resize_move/_resize_end，方便宿主窗口
    在全局事件过滤器里调用（因为子控件会吞掉鼠标事件，窗口级的
    mousePressEvent 在内容铺满时根本收不到）。
    """

    EDGE = 8               # 边缘命中宽度（px）
    MIN_W = 300
    MIN_H = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self._resizing = False
        self._edge = ""
        self._start_geo = None
        self._start_pos = None

    # 命中测试（局部坐标）
    def _hit_edge(self, pos) -> str:
        w, h, e = self.width(), self.height(), self.EDGE
        x, y = pos.x(), pos.y()
        if x < 0 or y < 0 or x > w or y > h:
            return ""
        left, right = x <= e, x >= w - e
        top, bottom = y <= e, y >= h - e
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return ""

    _CURSORS = {
        "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
        "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
        "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    }

    # ---------------------------------------------------------- 缩放内核
    def edge_at_global(self, gpos) -> str:
        """用全局坐标做边缘命中（顶层窗口用）。"""
        if not self.isVisible():
            return ""
        return self._hit_edge(self.mapFromGlobal(gpos))

    def _min_w(self) -> int:
        return max(self.MIN_W, self.minimumWidth())

    def _min_h(self) -> int:
        return max(1, self.minimumHeight())

    def _resize_begin(self, edge: str, gpos) -> None:
        self._resizing = True
        self._edge = edge
        self._start_geo = self.geometry()
        self._start_pos = QPoint(gpos)
        try:
            self.grabMouse()      # 拖出窗口也要收到事件
        except Exception:
            pass

    def _resize_move(self, gpos) -> None:
        if not (self._resizing and self._start_geo):
            return
        delta = QPoint(gpos) - self._start_pos
        g = self._start_geo
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        e = self._edge
        if "l" in e:
            x += delta.x(); w -= delta.x()
        if "r" in e:
            w += delta.x()
        if "t" in e:
            y += delta.y(); h -= delta.y()
        if "b" in e:
            h += delta.y()
        minw, minh = self._min_w(), self._min_h()
        # 左/上边被顶到最小值时，位置也要跟着钉住，否则窗口会整体平移
        if w < minw:
            if "l" in e:
                x = g.x() + g.width() - minw
            w = minw
        if h < minh:
            if "t" in e:
                y = g.y() + g.height() - minh
            h = minh
        self.setGeometry(int(x), int(y), int(w), int(h))

    def _resize_end(self) -> None:
        if not self._resizing:
            return
        self._resizing = False
        self._start_geo = None
        try:
            self.releaseMouse()
        except Exception:
            pass

    # 兜底：窗口自身收到鼠标事件时也能缩放
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_edge(ev.position().toPoint())
            if edge:
                self._resize_begin(edge, ev.globalPosition().toPoint())
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resizing:
            self._resize_move(ev.globalPosition().toPoint())
        else:
            edge = self._hit_edge(ev.position().toPoint())
            cur = self._CURSORS.get(edge)
            self.setCursor(cur if cur else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._resize_end()
        super().mouseReleaseEvent(ev)
