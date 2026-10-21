# -*- coding: utf-8 -*-
"""主界面：无边框阅读窗口 + 目录 / 设置 / 搜索 侧栏。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QSize, Signal, QPoint, QRect
from PySide6.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap,
                           QShortcut, QTextCharFormat, QTextCursor, QAction)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QScrollArea,
                               QScrollBar, QSizeGrip, QSlider, QStackedWidget,
                               QTextBrowser, QTextEdit, QToolButton, QVBoxLayout,
                               QWidget, QSystemTrayIcon, QGridLayout,
                               QFileDialog)

from config import Config, THEMES
from epub_parser import open_epub, open_book
import booklist as BL
from window_utils import (FramelessWindow, GlobalHotkey, HOTKEY_PRESETS, VK,
                          detect_capture, MOD_CONTROL, MOD_SHIFT, MOD_ALT)

APP_NAME = "幽灵阅读器"


def qss_color(c: str, alpha=1.0) -> str:
    col = QColor(c)
    return f"rgba({col.red()},{col.green()},{col.blue()},{alpha})"


# ================================================================= 工具条按钮

class IconButton(QToolButton):
    def __init__(self, text: str, tip: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(30, 26)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("""
            QToolButton { border:none; border-radius:5px; color:#9a9a9e;
                          font-size:14px; background:transparent; }
            QToolButton:hover { background:rgba(255,255,255,0.10); color:#fff; }
            QToolButton:checked { background:rgba(255,255,255,0.16); color:#fff; }
        """)


# ================================================================= 目录面板

class TocPanel(QWidget):
    chapter_picked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 10)
        lay.setSpacing(7)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("筛选章节名…")
        self.filter.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.07);border:none;border-radius:5px;"
            "padding:6px 9px;color:#dcdce0;font-size:12px;}")
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setStyleSheet("""
            QListWidget{background:transparent;border:none;color:#c4c4c8;
                        font-size:13px;outline:none;}
            QListWidget::item{padding:7px 8px;border-radius:5px;}
            QListWidget::item:hover{background:rgba(255,255,255,0.07);}
            QListWidget::item:selected{background:rgba(94,160,255,0.26);color:#fff;}
            QScrollBar:vertical{background:transparent;width:7px;margin:0;}
            QScrollBar::handle:vertical{background:rgba(255,255,255,0.20);
                                        border-radius:3px;min-height:28px;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0;}
            QScrollBar:horizontal{height:0;}
        """)
        self.list.itemClicked.connect(self._on_click)
        lay.addWidget(self.list, 1)

        self._titles: list = []
        self._count = 0

    def set_chapters(self, titles):
        self._titles = list(titles)
        self._count = len(titles)
        self._rebuild(list(enumerate(self._titles)))

    def _rebuild(self, items):
        """items 是 [(原章节索引, 标题)]。

        注意：UserRole 必须存**原章节索引**，不能存列表行号。
        筛选后行号会变，若存行号则点第 3 行会跳到原书第 3 章 —— 章节对不上。
        """
        self.list.clear()
        for idx, t in items:
            it = QListWidgetItem(t)
            it.setData(Qt.ItemDataRole.UserRole, idx)
            self.list.addItem(it)

    def _apply_filter(self, kw):
        kw = kw.strip()
        if not kw:
            self._rebuild(list(enumerate(self._titles)))
            return
        self._rebuild([(i, t) for i, t in enumerate(self._titles) if kw in t])

    def _on_click(self, item):
        self.chapter_picked.emit(item.data(Qt.ItemDataRole.UserRole))

    def highlight(self, index: int):
        for r in range(self.list.count()):
            it = self.list.item(r)
            if it.data(Qt.ItemDataRole.UserRole) == index:
                self.list.setCurrentItem(it)
                self.list.scrollToItem(it, QListWidget.ScrollHint.PositionAtCenter)
                return


# ================================================================= 搜索面板

class SearchPanel(QWidget):
    jump = Signal(int, str)
    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 10)
        lay.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText("全文搜索…")
        self.input.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.07);border:none;border-radius:5px;"
            "padding:6px 9px;color:#dcdce0;font-size:12px;}")
        self.input.returnPressed.connect(self._go)
        btn = QPushButton("搜索")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(52)
        btn.setStyleSheet(
            "QPushButton{background:rgba(94,160,255,0.24);border:none;border-radius:5px;"
            "color:#dbe8ff;font-size:12px;padding:6px 0;}"
            "QPushButton:hover{background:rgba(94,160,255,0.38);}")
        btn.clicked.connect(self._go)
        row.addWidget(self.input, 1)
        row.addWidget(btn)
        lay.addLayout(row)

        self.info = QLabel("输入关键词后回车")
        self.info.setStyleSheet("color:#7d7d84;font-size:11px;padding-left:2px;")
        lay.addWidget(self.info)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setStyleSheet("""
            QListWidget{background:transparent;border:none;color:#c4c4c8;
                        font-size:12px;outline:none;}
            QListWidget::item{padding:7px 8px;border-radius:5px;
                              border-bottom:1px solid rgba(255,255,255,0.05);}
            QListWidget::item:hover{background:rgba(255,255,255,0.07);}
            QListWidget::item:selected{background:rgba(94,160,255,0.26);color:#fff;}
            QScrollBar:vertical{background:transparent;width:7px;margin:0;}
            QScrollBar::handle:vertical{background:rgba(255,255,255,0.20);
                                        border-radius:3px;min-height:28px;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0;}
            QScrollBar:horizontal{height:0;}
        """)
        self.list.itemClicked.connect(self._on_click)
        lay.addWidget(self.list, 1)
        self._hits = []

    def _go(self):
        kw = self.input.text().strip()
        if kw:
            self.search_requested.emit(kw)

    def show_results(self, hits, keyword):
        self._hits = hits
        self.list.clear()
        if not hits:
            self.info.setText(f"没有找到「{keyword}」")
            return
        self.info.setText(f"共 {len(hits)} 处命中，点击跳转")
        for idx, title, snip in hits:
            it = QListWidgetItem(f"{title}\n{snip}")
            it.setData(Qt.ItemDataRole.UserRole, (idx, keyword))
            self.list.addItem(it)

    def _on_click(self, item):
        idx, kw = item.data(Qt.ItemDataRole.UserRole)
        self.jump.emit(idx, kw)


# ================================================================= 设置面板

class SettingsPanel(QWidget):
    changed = Signal(str, object)

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea{background:transparent;border:none;}
            QScrollBar:vertical{background:transparent;width:7px;}
            QScrollBar::handle:vertical{background:rgba(255,255,255,0.20);
                                        border-radius:3px;min-height:28px;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0;}
        """)
        outer.addWidget(scroll)

        host = QWidget()
        host.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(12, 8, 10, 14)
        lay.setSpacing(6)
        scroll.setWidget(host)

        def section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(
                "color:#7f8a9c;font-size:11px;font-weight:600;"
                "padding:11px 0 3px 1px;letter-spacing:1px;")
            lay.addWidget(lbl)

        def slider_row(label, key, lo, hi, suffix="", step=1, fmt=None, scale=1.0):
            """scale=100 表示配置里存 0~1 浮点，滑块用 0~100 整数。"""
            box = QWidget(); bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(2)
            head = QHBoxLayout()
            name = QLabel(label); name.setStyleSheet("color:#c4c4c8;font-size:12px;")
            val = QLabel(""); val.setStyleSheet("color:#8fb4ff;font-size:11px;")
            head.addWidget(name); head.addStretch(1); head.addWidget(val)
            bl.addLayout(head)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi); s.setSingleStep(step)

            # 把配置值安全地转成滑块刻度
            raw = self.cfg.get(key)
            try:
                raw = float(raw)
            except (TypeError, ValueError):
                raw = float(lo)
            if scale != 1.0:
                # 存的是 0~1 浮点就 *100；若已经是百分比则原样使用
                tick = raw * 100.0 if raw <= 1.5 else raw
            else:
                tick = raw
            s.setValue(int(max(lo, min(hi, round(tick)))))

            s.setStyleSheet("""
                QSlider::groove:horizontal{height:4px;background:rgba(255,255,255,0.14);
                                           border-radius:2px;}
                QSlider::sub-page:horizontal{background:#5EA0FF;border-radius:2px;}
                QSlider::handle:horizontal{background:#f0f0f2;width:13px;height:13px;
                                           margin:-5px 0;border-radius:6px;}
            """)

            def update(v):
                if fmt:
                    val.setText(fmt(v))
                else:
                    val.setText(f"{v}{suffix}")
                self.cfg.set(key, v / scale if scale != 1.0 else v)
                self.changed.emit(key, v / scale if scale != 1.0 else v)

            s.valueChanged.connect(update)
            update(s.value())
            bl.addWidget(s)
            lay.addWidget(box)

        # ---------------- 外观
        section("外观")
        slider_row("窗口不透明度", "opacity", 15, 100, "%",
                   fmt=lambda v: f"{v}%", scale=100.0)
        slider_row("文字保护（文字保实、背景变透）", "text_protect", 0, 100, "%",
                   fmt=lambda v: "关闭" if v == 0 else f"{v}%")

        themes_box = QWidget(); tl = QVBoxLayout(themes_box)
        tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(5)
        tl.addWidget(self._mini_label("纯色主题"))
        grid = QGridLayout(); grid.setSpacing(6)
        self._theme_btns = []
        for i, (name, bg, fg, light) in enumerate(THEMES):
            b = QPushButton(name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            b.setFixedHeight(27)
            b.setStyleSheet(f"""
                QPushButton{{background:{bg};color:{fg};border:1px solid rgba(255,255,255,0.16);
                             border-radius:5px;font-size:11px;}}
                QPushButton:hover{{border:1px solid rgba(255,255,255,0.42);}}
                QPushButton:checked{{border:1.5px solid #5EA0FF;}}
            """)
            b.clicked.connect(lambda _=False, t=(bg, fg): self._pick_theme(t))
            grid.addWidget(b, i // 3, i % 3)
            self._theme_btns.append(b)
        self._mark_theme(self.cfg.get("bg_color"))
        tl.addLayout(grid)
        lay.addWidget(themes_box)

        slider_row("背景明暗微调", "paper_gamma", -40, 40, "",
                   fmt=lambda v: f"{v:+d}" if v else "0")

        # ---------------- 文字
        section("文字")
        f_box = QWidget(); fl = QVBoxLayout(f_box)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(5)
        fl.addWidget(self._mini_label("正文字体"))
        self.font_combo = QComboBox()
        self.font_combo.addItems([
            "微软雅黑", "宋体", "楷体", "仿宋", "思源黑体", "思源宋体",
            "黑体", "华文中宋", "等线", "Verdana", "Georgia", "Consolas",
        ])
        self.font_combo.setCurrentText(self.cfg.get("chinese_font"))
        self._style_combo(self.font_combo)
        self.font_combo.currentTextChanged.connect(
            lambda t: self.changed.emit("chinese_font", t))
        fl.addWidget(self.font_combo)
        fl.addWidget(self._mini_label("标题字体"))
        self.title_combo = QComboBox()
        self.title_combo.addItems(["宋体", "微软雅黑", "楷体", "华文中宋", "黑体"])
        self.title_combo.setCurrentText(self.cfg.get("title_font"))
        self._style_combo(self.title_combo)
        self.title_combo.currentTextChanged.connect(
            lambda t: self.changed.emit("title_font", t))
        fl.addWidget(self.title_combo)
        lay.addWidget(f_box)

        slider_row("字号", "font_size", 11, 40, " px")
        slider_row("字重", "font_weight", 300, 900, "", step=100,
                   fmt=lambda v: {300: "细", 400: "常规", 500: "中等",
                                  600: "半粗", 700: "粗体", 800: "特粗",
                                  900: "极粗"}.get(v, str(v)))
        slider_row("行距", "line_height", 110, 300, "%")
        slider_row("字间距", "letter_spacing", 80, 300, "%")

        # ---------------- 阅读
        section("阅读")
        mode = QWidget(); ml = QVBoxLayout(mode)
        ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(5)
        ml.addWidget(self._mini_label("翻页方式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["滚动模式", "翻页模式"])
        self.mode_combo.setCurrentIndex(0 if self.cfg.get("page_mode") == "scroll" else 1)
        self._style_combo(self.mode_combo)
        self.mode_combo.currentIndexChanged.connect(
            lambda i: self.changed.emit("page_mode", "scroll" if i == 0 else "page"))
        ml.addWidget(self.mode_combo)
        lay.addWidget(mode)

        # ---------------- 隐私
        section("隐私 / 防窥")
        self.chk_top = self._checkbox("窗口始终置顶", self.cfg.get("always_on_top"))
        self.chk_top.toggled.connect(lambda v: self.changed.emit("always_on_top", v))
        lay.addWidget(self.chk_top)

        self.chk_protect = self._checkbox("防截屏模式（OBS/录屏中自动隐藏）", False)
        self.chk_protect.toggled.connect(lambda v: self.changed.emit("capture_guard", v))
        lay.addWidget(self.chk_protect)

        tip = QLabel("热键：Ctrl+` 隐藏 / 恢复窗口（可在下方更换）")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#7d7d84;font-size:11px;padding:2px 1px;")
        lay.addWidget(tip)

        hk_box = QWidget(); hl = QVBoxLayout(hk_box)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(5)
        hl.addWidget(self._mini_label("隐藏窗口热键"))
        self.hotkey_combo = QComboBox()
        self.hotkey_combo.addItems([h[0] for h in HOTKEY_PRESETS])
        self._style_combo(self.hotkey_combo)
        self.hotkey_combo.currentIndexChanged.connect(
            lambda i: self.changed.emit("hotkey_index", i))
        hl.addWidget(self.hotkey_combo)
        lay.addWidget(hk_box)

        lay.addStretch(1)

        # ---------------- 关于
        section("快捷键一览")
        about = QLabel(
            "空格 / →      下一章\n"
            "← / PgUp    上一章\n"
            "↑ / ↓         上下滚动\n"
            "Ctrl + G     跳转章节\n"
            "Ctrl + F     全文搜索\n"
            "Ctrl + O     打开书籍\n"
            "Ctrl + 0     重置字号\n"
            "Ctrl + `     隐藏窗口\n"
            "Esc           隐藏窗口\n"
        )
        about.setStyleSheet(
            "color:#8b8b92;font-size:11px;line-height:170%;"
            "font-family:Consolas,'微软雅黑';")
        lay.addWidget(about)

    # ---- 辅助
    def _mini_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#8b8b92;font-size:11px;padding-top:3px;")
        return lbl

    def _style_combo(self, cb):
        cb.setStyleSheet("""
            QComboBox{background:rgba(255,255,255,0.07);border:none;border-radius:5px;
                      padding:5px 9px;color:#dcdce0;font-size:12px;}
            QComboBox::drop-down{border:none;width:18px;}
            QComboBox QAbstractItemView{background:#2A2A2E;color:#dcdce0;
                      border:1px solid rgba(255,255,255,0.14);
                      selection-background-color:#3D6FBF;outline:none;}
        """)

    def _checkbox(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(bool(checked))
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet("""
            QCheckBox{color:#c4c4c8;font-size:12px;spacing:7px;padding:3px 0;}
            QCheckBox::indicator{width:14px;height:14px;border-radius:3px;
                border:1px solid rgba(255,255,255,0.28);background:transparent;}
            QCheckBox::indicator:checked{background:#5EA0FF;
                border:1px solid #5EA0FF;}
        """)
        return cb

    def _pick_theme(self, theme):
        bg, fg = theme
        self.cfg.set("bg_color", bg)
        self.cfg.set("fg_color", fg)
        self._mark_theme(bg)
        self.changed.emit("bg_color", bg)
        self.changed.emit("fg_color", fg)

    def _mark_theme(self, bg):
        for b, t in zip(self._theme_btns, THEMES):
            b.setChecked(t[1].lower() == str(bg).lower())


# ================================================================= 发现好书

class DiscoverPanel(QWidget):
    """内置精选书单：分类浏览 + 一键跳正版平台。"""

    open_search = Signal(str)      # 书名 → 起点中文网
    open_weread = Signal(str)      # 书名 → 微信读书
    open_wiki = Signal(str)        # 书名（看简介/评价）

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 10)
        lay.setSpacing(7)

        head = QLabel(f"精选完本 · 共 {len(BL.BOOKLIST)} 本")
        head.setStyleSheet("color:#8fb4ff;font-size:12px;font-weight:600;padding-left:1px;")
        lay.addWidget(head)

        tip = QLabel("点书在正版平台查看（起点 / 微信读书）。"
                     "本软件只收录书目信息，不含正文。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#75757c;font-size:11px;line-height:150%;")
        lay.addWidget(tip)

        row = QHBoxLayout(); row.setSpacing(6)
        self.genre = QComboBox()
        self.genre.addItem("全部题材")
        for g in BL.all_genres():
            self.genre.addItem(g)
        self.genre.setStyleSheet("""
            QComboBox{background:rgba(255,255,255,0.07);border:none;border-radius:5px;
                      padding:5px 9px;color:#dcdce0;font-size:12px;}
            QComboBox::drop-down{border:none;width:18px;}
            QComboBox QAbstractItemView{background:#2A2A2E;color:#dcdce0;
                      border:1px solid rgba(255,255,255,0.14);
                      selection-background-color:#3D6FBF;outline:none;}
        """)
        self.genre.currentIndexChanged.connect(self._refresh)
        self.kw = QLineEdit()
        self.kw.setPlaceholderText("筛选书名 / 作者…")
        self.kw.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.07);border:none;border-radius:5px;"
            "padding:6px 9px;color:#dcdce0;font-size:12px;}")
        self.kw.textChanged.connect(self._refresh)
        row.addWidget(self.genre, 1)
        row.addWidget(self.kw, 1)
        lay.addLayout(row)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.setStyleSheet("""
            QListWidget{background:transparent;border:none;color:#c4c4c8;
                        font-size:12px;outline:none;}
            QListWidget::item{padding:8px;border-radius:6px;margin-bottom:3px;
                              background:rgba(255,255,255,0.035);}
            QListWidget::item:hover{background:rgba(255,255,255,0.085);}
            QListWidget::item:selected{background:rgba(94,160,255,0.26);color:#fff;}
            QScrollBar:vertical{background:transparent;width:7px;margin:0;}
            QScrollBar::handle:vertical{background:rgba(255,255,255,0.20);
                                        border-radius:3px;min-height:28px;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0;}
            QScrollBar:horizontal{height:0;}
        """)
        self.list.itemClicked.connect(self._on_click)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)
        lay.addWidget(self.list, 1)

        self._refresh()

    def _refresh(self):
        g = self.genre.currentText()
        kw = self.kw.text().strip()
        items = BL.BOOKLIST
        if g != "全部题材":
            items = [b for b in items if b["genre"] == g]
        if kw:
            items = [b for b in items
                     if kw in b["title"] or kw in b["author"] or kw in b["genre"]]
        self.list.clear()
        for b in items:
            txt = (f"{b['title']}　·　{b['author']}\n"
                   f"{b['genre']} · {b['words']}万字 · 已完结\n"
                   f"{b['desc']}\n💡 {b['why']}")
            it = QListWidgetItem(txt)
            it.setData(Qt.ItemDataRole.UserRole, b["title"])
            self.list.addItem(it)

    def _on_click(self, item):
        self.open_search.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        title = item.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction("在起点中文网查看", lambda: self.open_search.emit(title))
        m.addAction("在微信读书查看", lambda: self.open_weread.emit(title))
        m.addSeparator()
        m.addAction("查看简介与评价", lambda: self.open_wiki.emit(title))
        m.exec(self.list.mapToGlobal(pos))


# ================================================================= 本地书库

class LibraryPanel(QWidget):
    """扫描本地文件夹，把 epub/txt 排列成书架。"""

    book_open = Signal(str)        # 文件路径
    scan_done = Signal(int)        # 扫描到多少本

    CARD_W, CARD_H = 152, 96

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.books = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 10)
        lay.setSpacing(7)

        head = QHBoxLayout()
        self.lbl = QLabel("本地书库")
        self.lbl.setStyleSheet("color:#8fb4ff;font-size:12px;font-weight:600;")
        head.addWidget(self.lbl); head.addStretch(1)
        lay.addLayout(head)

        row = QHBoxLayout(); row.setSpacing(6)
        b_scan = QPushButton("重新扫描")
        b_pick = QPushButton("换文件夹")
        for b in (b_scan, b_pick):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(27)
            b.setStyleSheet(
                "QPushButton{background:rgba(94,160,255,0.20);border:none;border-radius:5px;"
                "color:#dbe8ff;font-size:11px;padding:0 10px;}"
                "QPushButton:hover{background:rgba(94,160,255,0.36);}")
        b_scan.clicked.connect(lambda: self.scan(force=True))
        b_pick.clicked.connect(self.pick_folder)
        row.addWidget(b_scan); row.addWidget(b_pick)
        lay.addLayout(row)

        self.path_lbl = QLabel("")
        self.path_lbl.setWordWrap(True)
        self.path_lbl.setStyleSheet("color:#6a6a72;font-size:10px;")
        lay.addWidget(self.path_lbl)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet("""
            QListWidget{background:transparent;border:none;color:#c4c4c8;
                        font-size:12px;outline:none;}
            QListWidget::item{padding:7px 8px;border-radius:5px;
                              border-bottom:1px solid rgba(255,255,255,0.05);}
            QListWidget::item:hover{background:rgba(255,255,255,0.07);}
            QListWidget::item:selected{background:rgba(94,160,255,0.26);color:#fff;}
            QScrollBar:vertical{background:transparent;width:7px;margin:0;}
            QScrollBar::handle:vertical{background:rgba(255,255,255,0.20);
                                        border-radius:3px;min-height:28px;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0;}
            QScrollBar:horizontal{height:0;}
        """)
        self.list.itemDoubleClicked.connect(self._on_open)
        lay.addWidget(self.list, 1)

        self.scan()

    # ---------- 文件夹
    def folder(self) -> str:
        f = self.cfg.get("library_dir", "")
        if not f:
            f = os.path.join(os.path.expanduser("~"), "Documents", "小说")
        return f

    def pick_folder(self):
        start = self.folder()
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "选择小说文件夹", start)
        if d:
            self.cfg.set("library_dir", d)
            self.cfg.save()
            self.scan(force=True)

    # ---------- 扫描
    def scan(self, force=False):
        folder = self.folder()
        self.path_lbl.setText(folder)
        found = []
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                low = name.lower()
                if low.endswith((".epub", ".txt")):
                    full = os.path.join(folder, name)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        continue
                    found.append((name, full, size))
        found.sort(key=lambda x: x[0])

        self.books = found
        self.list.clear()
        for name, full, size in found:
            mb = size / 1024 / 1024
            ext = "EPUB" if name.lower().endswith(".epub") else "TXT"
            it = QListWidgetItem(f"{os.path.splitext(name)[0]}\n{ext} · {mb:.1f} MB")
            it.setData(Qt.ItemDataRole.UserRole, full)
            self.list.addItem(it)
        self.lbl.setText(f"本地书库 · {len(found)} 本")
        self.scan_done.emit(len(found))

    def _on_open(self, item):
        self.book_open.emit(item.data(Qt.ItemDataRole.UserRole))
