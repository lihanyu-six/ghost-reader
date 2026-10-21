# -*- coding: utf-8 -*-
"""幽灵阅读器主窗口。"""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import (Qt, QTimer, QSize, Signal, QPoint, QRectF, QEvent,
                            QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap,
                           QShortcut, QTextCharFormat, QTextCursor, QAction,
                           QFontDatabase, QLinearGradient, QBrush)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPushButton, QSizeGrip,
                               QStackedWidget, QTextBrowser, QTextEdit,
                               QVBoxLayout, QWidget, QSystemTrayIcon,
                               QGraphicsOpacityEffect, QFileDialog, QMessageBox,
                               QToolButton)

from config import Config, THEMES
from epub_parser import open_book
from panels import (TocPanel, SearchPanel, SettingsPanel, IconButton,
                    DiscoverPanel, LibraryPanel)
import booklist as BL
from window_utils import (FramelessWindow, GlobalHotkey, HOTKEY_PRESETS, VK,
                          detect_capture, set_taskbar_visible,
                          MOD_CONTROL, MOD_SHIFT, MOD_ALT)
import webbrowser

APP_NAME = "幽灵阅读器"
BG_ALPHA = 0.86          # 窗口背景色的基础不透明度（剩余部分交给窗口整体透明度）
MINI_MIN_H = 96          # 迷你模式下的最小高度


class ReaderView(QTextBrowser):
    """正文显示区，支持章节拼接、自动加载下一章、按章节滚动。"""

    need_next = Signal()
    need_prev = Signal()
    scrolled = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self._loading = False

    def wheelEvent(self, ev):
        super().wheelEvent(ev)

    def keyPressEvent(self, ev):
        k = ev.key()
        key = ev.key()
        mods = ev.modifiers()
        if mods == Qt.KeyboardModifier.NoModifier:
            if key in (Qt.Key.Key_Space, Qt.Key.Key_PageDown):
                self.verticalScrollBar().triggerAction(
                    self.verticalScrollBar().SliderAction.SliderPageStepAdd)
                self._check_end(); ev.accept(); return
            if key in (Qt.Key.Key_PageUp,):
                self.verticalScrollBar().triggerAction(
                    self.verticalScrollBar().SliderAction.SliderPageStepSub)
                ev.accept(); return
        super().keyPressEvent(ev)

    def _check_end(self):
        sb = self.verticalScrollBar()
        if sb.value() >= sb.maximum() - 2 and not self._loading:
            self._loading = True
            QTimer.singleShot(60, self._fire_next)

    def _fire_next(self):
        self._loading = False
        self.need_next.emit()


class GhostReader(FramelessWindow):

    def __init__(self, book_path: str = ""):
        super().__init__()
        self.cfg = Config()
        self.book = None
        self.chapter_index = 0
        self._rendered: list = []           # 已渲染到正文框的章节序号
        self._ch_pos: list = []             # [(文档位置, 章节序号)]，用于滚动定位
        self._appending = False             # 正在追加下一章（防重入）
        self._autoscroll = False
        self._autoscroll_speed = 1
        self._sidebar_open = False
        self._hidden = False
        self._dragging = False
        self._drag_offset = QPoint()
        self._last_save = 0.0
        self._maxed = False
        self._pre_max = None
        self._mini_on = False
        self._mini_geo = None
        self._cursor_overridden = False
        self._dragging_view = False

        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(int(self.cfg.get("width")), int(self.cfg.get("height")))
        self._sel_fonts = self._available_fonts()

        self._build_ui()
        self._build_tray()
        self._bind_shortcuts()
        self._apply_style()
        self._restore_geometry()
        self._setup_hotkey()

        # 全局事件过滤器：内容区铺满窗口时，边缘缩放事件会被子控件吞掉，
        # 必须在 app 层拦截才能实现「任意边缘都能拉」。
        try:
            QApplication.instance().installEventFilter(self)
        except Exception:
            pass

        # 自动滚动定时器
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(40)
        self._scroll_timer.timeout.connect(self._tick_autoscroll)

        # 防截屏轮询
        self._guard_timer = QTimer(self)
        self._guard_timer.setInterval(1200)
        self._guard_timer.timeout.connect(self._check_capture)
        self._capture_guard_on = False

        QTimer.singleShot(120, lambda: self._check_capture_target())
        if book_path:
            QTimer.singleShot(80, lambda: self.load_book(book_path))
        else:
            last = self.cfg.get("last_book", "")
            if last and os.path.exists(last):
                QTimer.singleShot(80, lambda: self.load_book(last))
            else:
                self._show_welcome()

    # ===================================================== 字体

    @staticmethod
    def _available_fonts() -> set:
        """返回系统已安装字体族的小写集合。"""
        names = set()
        try:
            for f in QFontDatabase.families():
                names.add(str(f).lower())
        except Exception:
            pass
        # offscreen / 无字体引擎时枚举为空，回退到系统字体目录
        if not names and sys.platform.startswith("win"):
            import glob
            fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            try:
                for path in glob.glob(os.path.join(fonts_dir, "*")):
                    try:
                        names.add(os.path.basename(path).lower())
                    except Exception:
                        continue
                # 用文件名 -> 族名 的关键字补充
                blob = " ".join(names)
                for kw in ("msyh", "simsun", "simhei", "simkai", "simfang",
                           "deng", "msjh", "mingliu", "kaiti", "fangsong"):
                    if kw in blob:
                        names.add(kw)
            except Exception:
                pass
        return names

    # 中文名 -> 实际字体族名
    FONT_ALIAS = {
        "微软雅黑": ("Microsoft YaHei", "msyh"),
        "宋体": ("SimSun", "simsun"),
        "楷体": ("KaiTi", "simkai"),
        "仿宋": ("FangSong", "simfang"),
        "黑体": ("SimHei", "simhei"),
        "等线": ("DengXian", "deng"),
        "华文中宋": ("STZhongsong", "stzhongs"),
        "思源黑体": ("Source Han Sans SC", "sourcehansans"),
        "思源宋体": ("Source Han Serif SC", "sourcehanserif"),
        "新宋体": ("NSimSun", "nsimsun"),
    }

    def _font_family(self, name: str, fallback="Microsoft YaHei") -> str:
        """把用户选择的字体名解析为可用字体；不可用则回退。"""
        if not name:
            return fallback
        low = name.lower()
        if low in self._sel_fonts:
            return name
        alias = self.FONT_ALIAS.get(name)
        if alias:
            for cand in alias:
                if cand.lower() in self._sel_fonts:
                    return cand
        # 枚举不可用（如某些无头环境）时直接信任用户选择
        if not self._sel_fonts:
            return alias[0] if alias else name
        # 英文字体直接匹配
        for f in self._sel_fonts:
            if low in f or f in low:
                return name
        return fallback

    # ===================================================== 界面构建

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 背景容器（承载圆角与半透明底）
        self.shell = QWidget(self)
        self.shell.setObjectName("shell")
        root.addWidget(self.shell)

        shell_lay = QVBoxLayout(self.shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)

        # ---------- 工具条
        self.topbar = QWidget(self.shell)
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(34)
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(8, 3, 6, 3)
        tb.setSpacing(3)

        self.lbl_title = QLabel("未打开书籍")
        self.lbl_title.setStyleSheet("color:#84848a;font-size:11px;padding-left:3px;")
        self.lbl_title.setMinimumWidth(60)

        self.btn_open = IconButton("📂", "打开书籍 (Ctrl+O)")
        self.btn_lib = IconButton("📚", "本地书库 (Ctrl+L)")
        self.btn_toc = IconButton("☰", "目录 (Ctrl+B)")
        self.btn_search = IconButton("🔍", "全文搜索 (Ctrl+F)")
        self.btn_discover = IconButton("✨", "发现好书 (Ctrl+D)")
        self.btn_settings = IconButton("⚙", "设置 (Ctrl+,)")
        self.btn_auto = IconButton("⏱", "自动滚动")
        self.btn_auto.setCheckable(True)
        self.btn_mini = IconButton("🗕", "迷你模式")
        self.btn_mini.setCheckable(True)
        self.btn_hide = IconButton("👁", "隐藏窗口 (Ctrl+`)")
        self.btn_close = IconButton("✕", "退出")

        tb.addWidget(self.btn_open)
        tb.addWidget(self.btn_lib)
        tb.addWidget(self.btn_toc)
        tb.addWidget(self.btn_search)
        tb.addWidget(self.btn_discover)
        tb.addWidget(self.btn_settings)
        tb.addWidget(self.btn_auto)
        tb.addWidget(self.btn_mini)
        tb.addStretch(1)
        tb.addWidget(self.lbl_title, 0)
        tb.addStretch(1)
        tb.addWidget(self.btn_hide)
        tb.addWidget(self.btn_close)

        # ---------- 主体：内容 + 侧栏
        body = QWidget(self.shell)
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # 内容栈：0=阅读  1=欢迎页
        self.stack = QStackedWidget(body)

        self.view = ReaderView(self.stack)
        self.view.need_next.connect(self.next_chapter)
        self.view.need_prev.connect(self.prev_chapter)
        self.view.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.stack.addWidget(self.view)

        # 欢迎页
        self.welcome = QWidget(self.stack)
        wl = QVBoxLayout(self.welcome)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(14)
        logo = QLabel("📖")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size:46px;")
        w1 = QLabel("幽灵阅读器")
        w1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w1.setStyleSheet("color:#c9c9cb;font-size:19px;font-weight:600;")
        w2 = QLabel("支持 EPUB / TXT  ·  半透明浮于桌面  ·  一键隐身")
        w2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w2.setStyleSheet("color:#75757c;font-size:12px;")
        self.w_btn = QPushButton("  打开一本书  ")
        self.w_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.w_btn.setStyleSheet(
            "QPushButton{background:rgba(94,160,255,0.22);border:1px solid rgba(94,160,255,0.5);"
            "border-radius:7px;color:#dbe8ff;font-size:13px;padding:8px 20px;}"
            "QPushButton:hover{background:rgba(94,160,255,0.36);}")
        self.w_btn.clicked.connect(self.open_dialog)

        wbtns = QHBoxLayout()
        wbtns.setSpacing(8)
        for text, idx in (("📚 本地书库", 4), ("✨ 发现好书", 3)):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,0.06);"
                "border:1px solid rgba(255,255,255,0.14);"
                "border-radius:7px;color:#c9c9cb;font-size:12px;padding:7px 14px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.13);}")
            b.clicked.connect(lambda _=False, i=idx: self.toggle_sidebar(i))
            wbtns.addWidget(b)

        self.w_recents = QLabel("")
        self.w_recents.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.w_recents.setStyleSheet("color:#6a6a72;font-size:11px;")
        wl.addStretch(2)
        wl.addWidget(logo)
        wl.addWidget(w1)
        wl.addWidget(w2)
        wl.addSpacing(6)
        wl.addWidget(self.w_btn, 0, Qt.AlignmentFlag.AlignCenter)
        wl.addLayout(wbtns)
        wl.addWidget(self.w_recents)
        wl.addStretch(3)
        self.stack.addWidget(self.welcome)

        body_lay.addWidget(self.stack, 1)

        # 侧栏
        self.sidebar = QWidget(body)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(0)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        self.panel_stack = QStackedWidget(self.sidebar)
        self.toc_panel = TocPanel(self.panel_stack)
        self.toc_panel.chapter_picked.connect(self.goto_chapter)
        self.search_panel = SearchPanel(self.panel_stack)
        self.search_panel.jump.connect(self._jump_to_hit)
        self.search_panel.search_requested.connect(self._do_search)
        self.settings_panel = SettingsPanel(self.cfg, self.panel_stack)
        self.settings_panel.changed.connect(self._on_setting_changed)
        self.discover_panel = DiscoverPanel(self.panel_stack)
        self.discover_panel.open_search.connect(self.open_book_search)
        self.discover_panel.open_weread.connect(self.open_book_weread)
        self.discover_panel.open_wiki.connect(self.open_book_wiki)
        self.library_panel = LibraryPanel(self.cfg, self.panel_stack)
        self.library_panel.book_open.connect(self.load_book)
        self.library_panel.scan_done.connect(self._on_library_scan)
        self.panel_stack.addWidget(self.toc_panel)
        self.panel_stack.addWidget(self.search_panel)
        self.panel_stack.addWidget(self.settings_panel)
        self.panel_stack.addWidget(self.discover_panel)
        self.panel_stack.addWidget(self.library_panel)
        sb_lay.addWidget(self.panel_stack)
        body_lay.addWidget(self.sidebar)

        shell_lay.addWidget(self.topbar)
        shell_lay.addWidget(body, 1)

        # 底部状态条
        self.statusbar = QWidget(self.shell)
        self.statusbar.setFixedHeight(22)
        sl = QHBoxLayout(self.statusbar)
        sl.setContentsMargins(10, 0, 8, 0)
        sl.setSpacing(10)
        self.lbl_chapter = QLabel("")
        self.lbl_chapter.setStyleSheet("color:#75757c;font-size:11px;")
        self.lbl_pct = QLabel("")
        self.lbl_pct.setStyleSheet("color:#75757c;font-size:11px;")
        self.lbl_opacity = QLabel("")
        self.lbl_opacity.setStyleSheet("color:#75757c;font-size:11px;")
        sl.addWidget(self.lbl_chapter, 1)
        sl.addWidget(self.lbl_pct)
        sl.addWidget(self.lbl_opacity)
        shell_lay.addWidget(self.statusbar)

        # ---------- 迷你模式条（默认隐藏）
        self.minibar = QWidget(self.shell)
        self.minibar.setFixedHeight(30)
        self.minibar.setVisible(False)
        ml = QHBoxLayout(self.minibar)
        ml.setContentsMargins(8, 2, 8, 2)
        ml.setSpacing(6)
        self.min_prev = IconButton("‹", "上一章")
        self.min_prev.setFixedSize(24, 24)
        self.min_next = IconButton("›", "下一章")
        self.min_next.setFixedSize(24, 24)
        self.min_restore = IconButton("⤢", "退出迷你模式")
        self.min_restore.setFixedSize(24, 24)
        ml.addWidget(self.min_prev)
        ml.addWidget(self.min_next)
        ml.addStretch(1)
        ml.addWidget(self.min_restore)
        shell_lay.addWidget(self.minibar)

        # ---------- 信号
        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_close.clicked.connect(self.quit_app)
        self.btn_hide.clicked.connect(self.toggle_hide)
        self.btn_lib.clicked.connect(lambda: self.toggle_sidebar(4))
        self.btn_toc.clicked.connect(lambda: self.toggle_sidebar(0))
        self.btn_search.clicked.connect(lambda: self.toggle_sidebar(1))
        self.btn_discover.clicked.connect(lambda: self.toggle_sidebar(3))
        self.btn_settings.clicked.connect(lambda: self.toggle_sidebar(2))
        self.btn_auto.toggled.connect(self.toggle_autoscroll)
        self.btn_mini.toggled.connect(self.toggle_mini)
        self.min_prev.clicked.connect(self.prev_chapter)
        self.min_next.clicked.connect(self.next_chapter)
        self.min_restore.clicked.connect(lambda: self.btn_mini.setChecked(False))

        self.topbar.installEventFilter(self)
        self.statusbar.installEventFilter(self)
        self.minibar.installEventFilter(self)
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.lbl_title.installEventFilter(self)

    # 这些控件可用来拖动整个窗口
    def _drag_handles(self) -> tuple:
        handles = [getattr(self, "topbar", None), getattr(self, "statusbar", None),
                   getattr(self, "minibar", None), getattr(self, "lbl_title", None)]
        return tuple(h for h in handles if h is not None)

    # ===================================================== 托盘

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._make_icon())
        self.tray.setToolTip(APP_NAME)

        m = QMenu()
        a_show = m.addAction("显示 / 隐藏窗口")
        a_show.triggered.connect(self.toggle_hide)
        m.addSeparator()
        a_open = m.addAction("打开书籍…")
        a_open.triggered.connect(self.open_dialog)
        a_lib = m.addAction("本地书库")
        a_lib.triggered.connect(lambda: (self.show_window(), self.toggle_sidebar(4)))
        a_disc = m.addAction("发现好书")
        a_disc.triggered.connect(lambda: (self.show_window(), self.toggle_sidebar(3)))
        a_toc = m.addAction("目录")
        a_toc.triggered.connect(lambda: (self.show_window(), self.toggle_sidebar(0)))
        a_set = m.addAction("设置")
        a_set.triggered.connect(lambda: (self.show_window(), self.toggle_sidebar(2)))
        m.addSeparator()

        op_menu = m.addMenu("透明度")
        self._op_actions = {}
        for pct in (30, 45, 60, 75, 85, 95, 100):
            act = op_menu.addAction(f"{pct}%")
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, p=pct: self.set_opacity(p / 100.0))
            self._op_actions[pct] = act

        m.addSeparator()
        a_quit = m.addAction("退出")
        a_quit.triggered.connect(self.quit_app)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    @staticmethod
    def _make_icon() -> QIcon:
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#5EA0FF"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(6, 10, 52, 44, 8, 8)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(12, 16, 40, 32, 4, 4)
        p.setBrush(QColor("#5EA0FF"))
        for i, y in enumerate((25, 32, 39)):
            w = 26 if i < 2 else 16
            p.drawRoundedRect(19, y, w, 3, 1.5, 1.5)
        p.end()
        return QIcon(pm)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_hide()

    # ===================================================== 快捷键

    def _bind_shortcuts(self):
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)
            s.activated.connect(fn)
            return s

        sc("Ctrl+O", self.open_dialog)
        sc("Ctrl+B", lambda: self.toggle_sidebar(0))
        sc("Ctrl+F", lambda: (self.show_window(), self.toggle_sidebar(1)))
        sc("Ctrl+,", lambda: self.toggle_sidebar(2))
        sc("Ctrl+D", lambda: (self.show_window(), self.toggle_sidebar(3)))
        sc("Ctrl+L", lambda: (self.show_window(), self.toggle_sidebar(4)))
        sc("Ctrl+R", self.rescan_library)
        sc("Ctrl+=", lambda: self._bump_font(1))
        sc("Ctrl+-", lambda: self._bump_font(-1))
        sc("Ctrl+0", lambda: self._set_font_size(17))
        sc("Ctrl+G", self.goto_dialog)
        sc("Ctrl+W", self.toggle_hide)
        # Esc 不挂 QShortcut：焦点在输入框/正文时会漏，改在 eventFilter 里拦
        sc("Right", self.next_chapter)
        sc("Left", self.prev_chapter)
        sc("PgDown", self.next_chapter)
        sc("PgUp", self.prev_chapter)

    def _setup_hotkey(self):
        self.hotkeys = GlobalHotkey(self)
        self.hotkeys.triggered.connect(self._on_hotkey)
        idx = int(self.cfg.get("hotkey_index", 0))
        idx = max(0, min(idx, len(HOTKEY_PRESETS) - 1))
        self._register_hotkey(idx)
        try:
            self.hotkeys.ensure_filter(QApplication.instance())
        except Exception:
            pass

    def _register_hotkey(self, idx: int):
        try:
            self.hotkeys.dispose()
        except Exception:
            pass
        name, vk, mods = HOTKEY_PRESETS[idx]
        ok = False
        try:
            ok = self.hotkeys.register("hide", vk, mods)
            self.hotkeys.ensure_filter(QApplication.instance())
        except Exception:
            ok = False
        self._hotkey_ok = ok
        self.cfg.set("hotkey_index", idx)
        if hasattr(self, "settings_panel"):
            self.settings_panel.hotkey_combo.blockSignals(True)
            self.settings_panel.hotkey_combo.setCurrentIndex(idx)
            self.settings_panel.hotkey_combo.blockSignals(False)

    def _on_hotkey(self, name):
        if name == "hide":
            self.toggle_hide()

    # ===================================================== 样式

    def _apply_style(self):
        bg = self.cfg.get("bg_color")
        fg = self.cfg.get("fg_color")
        gamma = int(self.cfg.get("paper_gamma", 0))
        col = QColor(bg)
        if gamma:
            col = col.lighter(100 + gamma) if gamma > 0 else col.darker(100 - gamma)
        # 文字保护：越高，背景越透（相对窗口透明度），文字越接近实心
        protect = max(0, min(100, int(self.cfg.get("text_protect", 0))))
        bg_alpha = BG_ALPHA * (1.0 - protect / 100.0 * 0.92)
        bg_rgb = f"rgba({col.red()},{col.green()},{col.blue()},{bg_alpha:.3f})"

        lite = QColor(fg)
        dim = lite.darker(140).name()
        mid = lite.darker(115).name()

        # 文字保护时，用纯色文字 + 描边阴影来对抗透明造成的发虚
        if protect > 0:
            w_op = float(self.cfg.get("opacity", 0.82))
            boost = 1.0 + protect / 100.0 * (1.0 / max(w_op, 0.2) - 1.0) * 0.85
            tcol = QColor(fg)
            tcol = tcol.lighter(int(boost * 100)) if w_op < 1.0 else tcol
            text_fg = tcol.name()
            shadow = "1px 0 2px rgba(0,0,0,0.55), 0 1px 2px rgba(0,0,0,0.45)"
        else:
            text_fg = fg
            shadow = "none"

        self.shell.setStyleSheet(f"""
            #shell {{
                background: {bg_rgb};
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
            }}
            #topbar, #statusbar, #minibar {{
                background: transparent;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }}
            #statusbar, #minibar {{ border-bottom: none; }}
            #sidebar {{
                background: rgba(255,255,255,0.030);
                border-left: 1px solid rgba(255,255,255,0.07);
            }}
        """)

        # 正文样式
        size = int(self.cfg.get("font_size"))
        lh = int(self.cfg.get("line_height")) / 100.0
        ls = int(self.cfg.get("letter_spacing")) / 100.0
        weight = int(self.cfg.get("font_weight", 400))
        fam = self._font_family(self.cfg.get("chinese_font"))
        tfam = self._font_family(self.cfg.get("title_font"), fam)

        self.view.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                border: none;
                color: {text_fg};
                padding: 26px 34px 60px 34px;
                selection-background-color: rgba(94,160,255,0.36);
                selection-color: #ffffff;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 2px 1px 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.16);
                border-radius: 4px; min-height: 34px;
            }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.30); }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        """)
        self._render_css = dict(
            size=size, lh=lh, ls=ls, weight=weight,
            fam=fam, tfam=tfam, fg=text_fg, mid=mid, dim=dim,
            shadow=shadow, protect=protect,
        )

        # 侧栏通用
        self.sidebar.setStyleSheet(f"""
            QWidget {{ color: {fg}; }}
            QLabel {{ color: {mid}; }}
        """)

        # 欢迎页与状态栏配色
        for w in (self.welcome, self.statusbar, self.topbar, self.minibar):
            w.setStyleSheet(f"background: transparent; color: {mid};")

        self.lbl_title.setStyleSheet(f"color:{dim};font-size:11px;padding-left:3px;")
        self.lbl_chapter.setStyleSheet(f"color:{dim};font-size:11px;")
        self.lbl_pct.setStyleSheet(f"color:{dim};font-size:11px;")
        self.lbl_opacity.setStyleSheet(f"color:{dim};font-size:11px;")
        self.w_recents.setStyleSheet(f"color:{dim};font-size:11px;")

        # 侧栏开关按钮外观
        base = "QToolButton{border:none;border-radius:5px;color:%s;font-size:14px;background:transparent;}"
        self.topbar.setStyleSheet("")
        for b in self.topbar.findChildren(QToolButton):
            b.setStyleSheet(
                base % mid
                + "QToolButton:hover{background:rgba(255,255,255,0.10);}"
                  "QToolButton:checked{background:rgba(255,255,255,0.16);}")

        # 重新渲染正文以应用字体
        if self.book:
            self._render_to(self.chapter_index, keep_scroll=True)

    # ===================================================== 渲染

    def _render_css_default(self):
        return dict(size=17, lh=1.85, ls=1.0, weight=400, fam="Microsoft YaHei",
                    tfam="SimSun", fg="#C9C9CB", mid="#8a8a90", dim="#75757c",
                    shadow="none", protect=0)

    def _render_to(self, index: int, keep_scroll=False, keyword=""):
        """从 index 开始渲染连续若干章到正文框。"""
        if not self.book:
            return
        css = getattr(self, "_render_css", None) or self._render_css_default()

        # 目标总字符数：约 3~4 屏
        target_chars = max(1800, int(self.view.viewport().height() / max(css["size"], 1) * 26))
        target_chars = min(target_chars, 26000)

        self._rendered = []
        parts = []
        total = 0
        i = index
        while i < self.book.chapter_count and total < target_chars:
            paras = self.book.chapter_paragraphs(i)
            title = self.book.chapter_title(i)
            body = "".join(paras)
            total += len(body)
            self._rendered.append(i)
            parts.append(self._html_chapter(title, paras, css, i))
            i += 1
            if len(self._rendered) >= 4:
                break

        html = ("<div style='margin:0;padding:0;'>" + "".join(parts) + "</div>")
        self._ch_pos = []                  # 旧索引先作废，等布局完再重建
        self.view.setHtml(html)
        self.chapter_index = index
        if not keep_scroll:
            self.view.verticalScrollBar().setValue(0)
        # 文档布局是延迟的，等一帧再建章节位置索引，否则 find 会落空
        QTimer.singleShot(0, self._index_chapters)
        self._update_status()
        if keyword:
            QTimer.singleShot(30, lambda: self._highlight_first(keyword))

    # ----------------------------------------------------- 章节位置索引

    def _index_chapters(self):
        """记录每个已渲染章节标题在文档里的字符位置。

        有了这张表，才能从滚动位置反推「用户现在看到的是第几章」，
        状态栏、目录高亮、阅读进度、以及「滚动到底续章」都依赖它。
        """
        self._ch_pos = []
        if not self.book or not self._rendered:
            return
        doc = self.view.document()
        pos = 0
        for idx in self._rendered:
            title = self.book.chapter_title(idx)
            if not title:
                continue
            cur = doc.find(title, pos)
            if cur.isNull():
                continue
            start = cur.selectionStart()
            self._ch_pos.append((start, idx))
            pos = start + 1

    def _chapter_at_viewport(self) -> int:
        """视口顶部对应的章节序号。"""
        if not self._ch_pos:
            return self.chapter_index
        try:
            cur = self.view.cursorForPosition(QPoint(4, 4))
            top = cur.position()
        except Exception:
            return self.chapter_index
        cur_idx = self._ch_pos[0][1]
        for start, idx in self._ch_pos:
            if start <= top:
                cur_idx = idx
            else:
                break
        return cur_idx

    # ----------------------------------------------------- 滚动续章

    def _maybe_append(self):
        """滚到已渲染内容末尾时，把下一章追加到文档尾部。

        用 insertHtml 追加而不是重绘整个文档：内容接在下面，
        滚动位置不动，读感是连续的，不会闪一下跳回顶部。
        """
        if self._appending or not self.book or not self._rendered:
            return
        if self._rendered[-1] + 1 >= self.book.chapter_count:
            return
        sb = self.view.verticalScrollBar()
        if sb.maximum() <= 0 or sb.value() < sb.maximum() - 4:
            return
        self._appending = True
        QTimer.singleShot(0, self._append_chapters)

    def _append_chapters(self, count: int = 3):
        self._appending = False
        if not self.book or not self._rendered:
            return
        nxt = self._rendered[-1] + 1
        if nxt >= self.book.chapter_count:
            return
        css = getattr(self, "_render_css", None) or self._render_css_default()
        parts = []
        added = 0
        while nxt < self.book.chapter_count and added < count:
            parts.append(self._html_chapter(
                self.book.chapter_title(nxt),
                self.book.chapter_paragraphs(nxt), css, nxt))
            self._rendered.append(nxt)
            nxt += 1
            added += 1
        if not parts:
            return
        cur = QTextCursor(self.view.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        # 必须先断开一个段落再插入：QTextCursor 位于既有段落末尾时，
        # insertHtml 会把块级元素当内联降级处理 —— 表现为下一章标题
        # 被塞到上一章最后一段的屁股后面。
        cur.insertBlock()
        cur.insertHtml("".join(parts))
        self._index_chapters()
        self._update_status()

    def _html_chapter(self, title: str, paras: list, css: dict, idx: int) -> str:
        tsize = int(css["size"] * 1.34)
        shadow = css.get("shadow", "none")
        shadow_css = ("text-shadow:" + shadow + ";") if shadow and shadow != "none" else ""
        head = (
            f"<div style=\"margin:6px 0 22px 0;\">"
            f"<span style='font-family:\"{css['tfam']}\";font-size:{tsize}px;"
            f"font-weight:600;color:{css['fg']};letter-spacing:1px;{shadow_css}'>"
            f"{self._esc(title)}</span>"
            f"<div style='height:1px;background:{css['dim']};opacity:0.35;"
            f"margin-top:13px;'></div>"
            f"</div>"
        )
        ps = []
        for p in paras:
            ps.append(
                f"<p style=\"margin:0 0 {int(css['size']*0.82)}px 0;"
                f"text-indent:{int(css['size']*2)}px;"
                f"line-height:{css['lh']};"
                f"letter-spacing:{css['ls']}px;"
                f"font-family:'{css['fam']}';"
                f"font-size:{css['size']}px;"
                f"{shadow_css}"
                f"font-weight:{css['weight']};\">"
                f"{self._esc(p)}</p>"
            )
        return f"<div id='ch{idx}' style='margin-bottom:30px;'>{head}{''.join(ps)}</div>"

    @staticmethod
    def _esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("  ", "&nbsp;&nbsp;"))

    def _highlight_first(self, keyword: str):
        doc = self.view.document()
        cursor = QTextCursor(doc)
        cursor = doc.find(keyword, cursor)
        if not cursor.isNull():
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 205, 60, 170))
            fmt.setForeground(QColor("#1a1a1a"))
            cursor.mergeCharFormat(fmt)
            self.view.setTextCursor(cursor)
            self.view.ensureCursorVisible()
            # 令高亮整体淡出
            QTimer.singleShot(2600, self._clear_highlight)

    def _clear_highlight(self):
        doc = self.view.document()
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.GlobalColor.transparent)
        fmt.setForeground(QColor(self.cfg.get("fg_color")))
        cur.mergeCharFormat(fmt)
        cur.clearSelection()
        c2 = QTextCursor(doc)
        c2.movePosition(QTextCursor.MoveOperation.Start)
        self.view.setTextCursor(c2)

    def _update_status(self):
        if not self.book:
            self.lbl_chapter.setText("")
            self.lbl_pct.setText("")
            return
        n = self.book.chapter_count
        pct = (self.chapter_index + 1) / max(n, 1) * 100
        title = self.book.chapter_title(self.chapter_index)
        self.lbl_chapter.setText(f"{self.chapter_index + 1}/{n}  {title[:22]}")
        self.lbl_pct.setText(f"{pct:.1f}%")
        self.lbl_opacity.setText(f"透明度 {int(self.windowOpacity() * 100)}%")
        self.lbl_title.setText(f"{self.book.title} · {self.book.author}")
        self.toc_panel.highlight(self.chapter_index)

    # ===================================================== 书籍加载

    def _show_welcome(self):
        self.stack.setCurrentIndex(1)
        recents = self.cfg.get("recent_books", [])
        if recents:
            names = " · ".join(os.path.basename(p) for p in recents[:2])
            self.w_recents.setText(f"最近：{names}")
        else:
            self.w_recents.setText("")

    def open_dialog(self):
        start = os.path.dirname(self.cfg.get("last_book", "")) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "打开书籍", start,
            "电子书 (*.epub *.txt);;EPUB (*.epub);;TXT (*.txt);;所有文件 (*)")
        if path:
            self.load_book(path)

    def load_book(self, path: str):
        try:
            if self.book:
                self.book.close()
            book = open_book(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法解析该文件：\n\n{e}")
            return

        self.book = book
        self.cfg.push_recent(path)
        # 同一本书才恢复上次进度，换书从第一章开始
        same_book = os.path.abspath(path).lower() == \
            os.path.abspath(self.cfg.get("last_book", "")).lower()
        start_ch = int(self.cfg.get("last_chapter", 0)) if same_book else 0
        self.cfg.set("last_book", path)
        self.cfg.save()

        self.toc_panel.set_chapters(
            [book.chapter_title(i) for i in range(book.chapter_count)])
        start_ch = max(0, min(start_ch, book.chapter_count - 1))

        self.stack.setCurrentIndex(0)
        self.chapter_index = start_ch
        self._render_to(start_ch)
        self.toc_panel.highlight(start_ch)

    # ===================================================== 导航

    def goto_chapter(self, index: int):
        if not self.book:
            return
        index = max(0, min(index, self.book.chapter_count - 1))
        self._render_to(index)
        self._save_progress()

    def _jump_to_hit(self, index: int, keyword: str):
        self._render_to(index, keyword=keyword)
        self.chapter_index = index
        self._save_progress()
        if self.sidebar.width() > 120:
            self.toggle_sidebar(self._sidebar_panel)

    def next_chapter(self, *_):
        if not self.book:
            return
        if self.chapter_index + 1 < self.book.chapter_count:
            self.goto_chapter(self.chapter_index + 1)

    def prev_chapter(self, *_):
        if not self.book:
            return
        if self.chapter_index > 0:
            self.goto_chapter(self.chapter_index - 1)

    def goto_dialog(self):
        if not self.book:
            return
        from PySide6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getInt(
            self, "跳转章节", f"章节号 (1 - {self.book.chapter_count})：",
            self.chapter_index + 1, 1, self.book.chapter_count)
        if ok:
            self.goto_chapter(val - 1)

    def _do_search(self, keyword: str):
        if not self.book:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            hits = self.book.search(keyword, limit=400)
        finally:
            QApplication.restoreOverrideCursor()
        self.search_panel.show_results(hits, keyword)

    def _on_scroll(self, _v):
        # 视口顶部落在哪一章，当前章节就是哪一章。
        # 这样状态栏、目录高亮、阅读进度都和眼睛看到的内容一致。
        idx = self._chapter_at_viewport()
        if idx != self.chapter_index:
            self.chapter_index = idx
            self._update_status()
        self._save_progress()
        # 滑到底自动接下一章
        self._maybe_append()

    def _save_progress(self):
        now = time.time()
        if now - self._last_save < 2.0:
            return
        self._last_save = now
        self.cfg.set("last_chapter", self.chapter_index)
        self.cfg.save()

    # ===================================================== 侧栏

    def toggle_sidebar(self, which: int):
        if self.sidebar.width() > 120 and self._sidebar_panel == which:
            self._animate_sidebar(0)
            return
        self._sidebar_panel = which
        self.panel_stack.setCurrentIndex(which)
        if which == 0 and self.book:
            self.toc_panel.highlight(self.chapter_index)
        self._animate_sidebar(320)

    def _animate_sidebar(self, target: int):
        self._sidebar_open = target > 0
        w = self._sidebar_panel if target > 0 else -1
        self.btn_toc.setChecked(w == 0)
        self.btn_search.setChecked(w == 1)
        self.btn_settings.setChecked(w == 2)
        self.btn_discover.setChecked(w == 3)
        self.btn_lib.setChecked(w == 4)
        self.anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim.setDuration(170)
        self.anim.setStartValue(self.sidebar.width())
        self.anim.setEndValue(target)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(
            lambda v: self.sidebar.setFixedWidth(int(v)))
        self.anim.start()

    # ===================================================== 发现好书 / 本地书库

    def open_book_search(self, title: str):
        """在系统浏览器打开起点中文网检索页（正版渠道）。"""
        self._open_url(BL.search_url(title))

    def open_book_weread(self, title: str):
        """在系统浏览器打开微信读书检索页（正版渠道）。"""
        self._open_url(BL.weread_url(title))

    def open_book_wiki(self, title: str):
        self._open_url(BL.info_url(title))

    def _open_url(self, url: str):
        try:
            webbrowser.open(url)
        except Exception:
            QMessageBox.information(self, "打开失败", f"请手动访问：\n{url}")

    def _on_library_scan(self, count: int):
        if count == 0:
            self.tray.showMessage(
                APP_NAME,
                "本地书库还没找到书。下载后放进文件夹，点「重新扫描」即可。",
                self._make_icon(), 3000)

    def rescan_library(self):
        self.library_panel.scan(force=True)

    # ===================================================== 设置响应

    def _on_setting_changed(self, key, value):
        if key == "opacity":
            # 面板已归一化为 0~1，set_opacity 自身也兼容百分比，直接透传
            self.set_opacity(value)
        elif key in ("chinese_font", "title_font", "bg_color", "fg_color",
                     "font_size", "line_height", "letter_spacing",
                     "font_weight", "paper_gamma", "text_protect"):
            # 面板已写 cfg，这里再写一次保证被外部直接调用时也生效
            self.cfg.set(key, value)
            self._apply_style()
        elif key == "page_mode":
            self.cfg.set("page_mode", value)
            self._apply_style()
        elif key == "always_on_top":
            self.cfg.set("always_on_top", bool(value))
            self._apply_flags()
        elif key == "capture_guard":
            self._enable_capture_guard(bool(value))
        elif key == "hotkey_index":
            self._register_hotkey(int(value))
        self.cfg.save()

    def set_opacity(self, value: float):
        """设置窗口整体不透明度。兼容传入 0~1 浮点或 0~100 百分比。"""
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.82
        if value > 1.5:          # 传进来的是百分比
            value /= 100.0
        value = max(0.15, min(1.0, value))
        self.setWindowOpacity(value)
        self.cfg.set("opacity", value)
        self.lbl_opacity.setText(f"透明度 {int(value * 100)}%")
        self.settings_panel.blockSignals(True)
        for pct, act in self._op_actions.items():
            act.setChecked(abs(pct / 100.0 - value) < 0.02)
        self.settings_panel.blockSignals(False)
        self.cfg.save()

    def toggle_autoscroll(self, on: bool):
        self._autoscroll = on
        if on:
            self._scroll_timer.start()
            self.btn_auto.setToolTip("自动滚动中（点击停止）")
        else:
            self._scroll_timer.stop()
            self.btn_auto.setToolTip("自动滚动")

    def _tick_autoscroll(self):
        if not self.book:
            return
        sb = self.view.verticalScrollBar()
        if sb.value() >= sb.maximum() - 1:
            self._maybe_append()          # 到末尾就顺着续下一章，不重绘
        if sb.value() < sb.maximum():
            sb.setValue(sb.value() + self._autoscroll_speed)

    def toggle_mini(self, on: bool):
        on = bool(on)
        self._mini_on = on
        self.topbar.setVisible(not on)
        self.statusbar.setVisible(not on)
        self.minibar.setVisible(on)
        self.btn_mini.setVisible(not on)
        if on:
            if not self._maxed:
                self._mini_geo = self.geometry()      # 记住原高度，退出时还原
            self.sidebar.setVisible(False)
            # 不锁死高度：压低最小值即可，仍可自由上下拉伸
            self.setMinimumHeight(MINI_MIN_H)
            self.resize(self.width(), max(MINI_MIN_H, int(self.height() * 0.62)))
        else:
            self.setMinimumHeight(self.MIN_H)
            self.sidebar.setVisible(True)
            g = self._mini_geo
            if g is not None:
                self.resize(self.width(), max(self.MIN_H, g.height()))
        # 迷你条出现/消失会改变可拖动区域，光标状态重置一下
        self._set_edge_cursor("")

    # ===================================================== 隐身

    def toggle_hide(self):
        """一键隐藏 / 恢复。

        判据只看真实可见性，不看 _hidden 标志。
        原因：任务栏按钮被点过、被投屏守卫 hide 过、被系统还原过，
        都会让 _hidden 和实际状态失步 —— 那时按 Esc 会走反分支，
        表现就是「按了没反应 / 要点好几次」。
        """
        if self.isVisible() and not self.isMinimized():
            self.hide_window()
        else:
            self.show_window()

    def hide_window(self):
        self._hidden = True
        self._save_progress()
        self._set_edge_cursor("")          # 别把缩放光标留到下次显示
        self.cfg.set("width", self.width())
        self.cfg.set("height", self.height())
        self.cfg.set("x", self.x())
        self.cfg.set("y", self.y())
        self.cfg.save()
        # 先 hide，再摘掉任务栏按钮：Qt 的 hide() 不会移除按钮，
        # 残留按钮被点击会把窗口又拉出来（这就是「点不消失」的根因）。
        self.hide()
        set_taskbar_visible(self, False)
        self.tray.showMessage(
            APP_NAME,
            f"已隐藏。按 {HOTKEY_PRESETS[int(self.cfg.get('hotkey_index', 0))][0]} 或点托盘图标恢复。",
            self._make_icon(), 1600)

    def show_window(self):
        self._hidden = False
        set_taskbar_visible(self, True)    # 先把任务栏按钮加回来
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, ev):
        """窗口状态被外部改动时，把任务栏按钮拉回与可见性一致的状态。

        不做「最小化就摘按钮」——最小化不是隐身，摘了用户就找不回来了。
        """
        super().changeEvent(ev)
        if ev.type() == QEvent.Type.WindowStateChange:
            if self.isVisible() and not self._hidden:
                set_taskbar_visible(self, True)

    def _enable_capture_guard(self, on: bool):
        self._capture_guard_on = on
        if on:
            self._guard_timer.start()
        else:
            self._guard_timer.stop()
            if self._hidden_by_guard:
                self.show_window()
                self._hidden_by_guard = False

    _hidden_by_guard = False

    def _check_capture(self):
        detected = detect_capture()
        if detected and self.isVisible():
            # 走和手动隐藏同一套逻辑，别让 _hidden 与真实可见性失步
            self._hidden_by_guard = True
            self._hidden = True
            self.hide()
            set_taskbar_visible(self, False)
        elif not detected and self._hidden_by_guard:
            self._hidden_by_guard = False
            self.show_window()

    # ===================================================== 拖拽 / 事件

    def _check_capture_target(self):
        """首次运行时检测是否有投屏软件，提示一次。"""
        if detect_capture():
            self.tray.showMessage(
                APP_NAME,
                "检测到投屏/录屏程序正在运行，建议在设置中开启「防截屏模式」。",
                self._make_icon(), 4000)

    # ===================================================== 光标 / 标题栏命中

    def _set_edge_cursor(self, edge: str):
        """在边缘显示缩放光标；离开时恢复。用 override 栈保证不被子控件覆盖。"""
        cur = self._CURSORS.get(edge)
        try:
            if cur:
                if self._cursor_overridden:
                    QApplication.changeOverrideCursor(cur)
                else:
                    QApplication.setOverrideCursor(cur)
                    self._cursor_overridden = True
            elif self._cursor_overridden:
                QApplication.restoreOverrideCursor()
                self._cursor_overridden = False
        except Exception:
            self._cursor_overridden = False

    def _on_titlebar(self, gpos) -> bool:
        """全局坐标是否落在「标题条」上（正常=工具条，迷你=迷你条）。"""
        bar = self.minibar if self._mini_on else self.topbar
        if bar is None or not bar.isVisible():
            return False
        local = bar.mapFromGlobal(gpos)
        return 0 <= local.x() <= bar.width() and 0 <= local.y() <= bar.height()

    def _remember_geometry(self):
        self.cfg.set("width", self.width())
        self.cfg.set("height", self.height())
        self.cfg.set("x", self.x())
        self.cfg.set("y", self.y())
        self.cfg.save()

    def eventFilter(self, obj, ev):
        try:
            t = ev.type()

            # ---------- Esc 一键隐藏（应用级拦截）
            # 原来挂在 QShortcut 上，焦点在侧栏输入框 / 正文 / 下拉里时会漏掉，
            # 表现就是「按 Esc 有时候不消失」。这里在应用层拦，谁有焦点都收得到。
            # 模态对话框（打开书籍、跳转章节、消息框）自己处理 Esc，不要抢。
            if t == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
                if QApplication.activeModalWidget() is None:
                    if self.isVisible() and not self.isMinimized():
                        self.hide_window()
                        return True

            # ---------- 全局鼠标：边缘缩放的唯一可靠入口
            # 内容区铺满窗口，边缘的鼠标事件会被 textBrowser 等子控件吃掉，
            # 窗口自身的 mousePressEvent 永远收不到，所以在这里统一拦截。
            if isinstance(obj, QWidget) and obj.window() is self:
                gpos = None
                if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
                         QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
                    try:
                        gpos = ev.globalPosition().toPoint()
                    except Exception:
                        gpos = None
                if gpos is not None:
                    if t == QEvent.Type.MouseMove:
                        if self._resizing:
                            self._resize_move(gpos)
                            return True
                        self._set_edge_cursor(self.edge_at_global(gpos))
                    elif t == QEvent.Type.MouseButtonPress and \
                            ev.button() == Qt.MouseButton.LeftButton:
                        edge = self.edge_at_global(gpos)
                        if edge:
                            self._resize_begin(edge, gpos)
                            self._set_edge_cursor(edge)
                            return True
                    elif t == QEvent.Type.MouseButtonRelease:
                        if self._resizing:
                            self._resize_end()
                            self._set_edge_cursor("")
                            self._remember_geometry()
                            return True
                    elif t == QEvent.Type.MouseButtonDblClick and \
                            ev.button() == Qt.MouseButton.LeftButton:
                        if self.edge_at_global(gpos):
                            return True                     # 边缘双击不做任何事
                        if self._on_titlebar(gpos):
                            if self._mini_on:
                                self.btn_mini.setChecked(False)   # 迷你模式：双击还原
                            else:
                                self.toggle_max()
                            return True

            # ---------- 拖动窗口（工具条 / 迷你条）
            if obj in self._drag_handles():
                if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                    gp = ev.globalPosition().toPoint()
                    if self._maxed:
                        # 最大化状态下拖动 → 先还原，并把光标保持在原相对位置
                        ratio = gp.x() / max(1, self.width())
                        self.toggle_max()
                        self._drag_offset = QPoint(int(self.width() * ratio), 16)
                    else:
                        self._drag_offset = gp - self.frameGeometry().topLeft()
                    self._dragging = True
                    self._set_edge_cursor("")
                    return False
                if t == QEvent.Type.MouseMove and self._dragging:
                    self.move(ev.globalPosition().toPoint() - self._drag_offset)
                    return False
                if t == QEvent.Type.MouseButtonRelease:
                    if self._dragging:
                        self._dragging = False
                        self._remember_geometry()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._mini_on:
                self.btn_mini.setChecked(False)          # 迷你模式双击 → 还原（不最大化）
                ev.accept()
                return
            if ev.position().y() <= self.topbar.height() + 4:
                self.toggle_max()
                ev.accept()
                return
        super().mouseDoubleClickEvent(ev)

    def toggle_max(self):
        if self._maxed:
            if self._pre_max is not None:
                self.setGeometry(self._pre_max)
            self._maxed = False
        else:
            self._pre_max = self.geometry()
            scr = self.screen().availableGeometry()
            self.setGeometry(scr)
            self._maxed = True
        self._set_edge_cursor("")

    def _apply_flags(self):
        flags = self.windowFlags()
        if self.cfg.get("always_on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _restore_geometry(self):
        x, y = int(self.cfg.get("x", -1)), int(self.cfg.get("y", -1))
        w, h = int(self.cfg.get("width", 560)), int(self.cfg.get("height", 760))
        if x < 0 or y < 0:
            scr = QApplication.primaryScreen().availableGeometry()
            x = scr.width() - w - 60
            y = 80
        self.setGeometry(x, y, w, h)
        if self.cfg.get("always_on_top"):
            self._apply_flags()
        self.setWindowOpacity(float(self.cfg.get("opacity", 0.82)))
        self.lbl_opacity.setText(f"透明度 {int(self.windowOpacity() * 100)}%")

    def _bump_font(self, delta: int):
        self._set_font_size(int(self.cfg.get("font_size")) + delta)

    def _set_font_size(self, size: int):
        size = max(11, min(40, size))
        self.cfg.set("font_size", size)
        self.settings_panel.findChild(QWidget)  # noqa
        self._apply_style()
        self.cfg.save()

    # ===================================================== 右键菜单

    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.addAction("本地书库", lambda: self.toggle_sidebar(4))
        m.addAction("发现好书", lambda: self.toggle_sidebar(3))
        m.addAction("目录", lambda: self.toggle_sidebar(0))
        m.addAction("搜索", lambda: self.toggle_sidebar(1))
        m.addAction("设置", lambda: self.toggle_sidebar(2))
        m.addSeparator()
        m.addAction("上一章 (←)", self.prev_chapter)
        m.addAction("下一章 (→)", self.next_chapter)
        m.addSeparator()
        sub = m.addMenu("窗口透明度")
        for pct in (30, 45, 60, 75, 85, 95, 100):
            a = sub.addAction(f"{pct}%")
            a.setCheckable(True)
            a.setChecked(abs(pct / 100.0 - self.windowOpacity()) < 0.02)
            a.triggered.connect(lambda _=False, p=pct: self.set_opacity(p / 100.0))
        m.addSeparator()
        m.addAction("隐藏窗口", self.toggle_hide)
        m.addAction("退出", self.quit_app)
        m.exec(ev.globalPos())

    # ===================================================== 关闭

    def closeEvent(self, ev):
        if getattr(self, "_really_quit", False):
            ev.accept()
            return
        ev.ignore()
        self.hide_window()

    def quit_app(self):
        self._really_quit = True
        try:
            self._set_edge_cursor("")
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        try:
            self.cfg.set("width", self.width())
            self.cfg.set("height", self.height())
            self.cfg.set("x", self.x())
            self.cfg.set("y", self.y())
            self.cfg.set("last_chapter", self.chapter_index)
            self.cfg.save()
            if self.book:
                self.book.close()
            self.hotkeys.dispose()
            self.tray.hide()
        except Exception:
            pass
        QApplication.quit()
