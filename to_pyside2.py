# -*- coding: utf-8 -*-
"""PySide6 → PySide2 兼容转换器

用途：为 Windows 7 构建兼容版。源码保持 PySide6 写法（主仓库不动），
本脚本在打包前生成一份 PySide2 版本到 win7_build/ 目录。

转换规则
1. 导入：`from PySide6.xxx import ...` → `from PySide2.xxx import ...`
2. Qt 枚举作用域：PySide6 的 `Qt.Scope.Name` → PySide2 的 `Qt.Name`
   （PySide2 的枚举都是扁平的，直接挂在 Qt 下）
3. 个别 API 名称差异
"""
import os
import re
import shutil
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SRC_DIR, "win7_build")

# 源码模块（不含 make_icon，它只在开发时用）
MODULES = ["main.py", "main_window.py", "panels.py", "epub_parser.py",
           "config.py", "window_utils.py", "booklist.py"]

# Qt 枚举作用域名（PySide6）→ 需要剥离的中间层
# PySide2 里 Qt.WindowType.Window 写作 Qt.Window
QT_SCOPES = [
    "WindowType", "WidgetAttribute", "MouseButton", "CursorShape",
    "ItemDataRole", "AlignmentFlag", "ScrollBarPolicy", "Event",
    "FocusPolicy", "Key", "WindowState", "ToolButtonStyle",
    "AspectRatioMode", "TransformationMode", "TextInteractionFlag",
    "PenStyle", "BrushStyle", "GlobalColor", "ImageFormat",
    "ContextMenuPolicy", "CheckState", "Orientation", "SizePolicy",
    "LayoutDirection", "DropAction", "KeyboardModifier", "TextElideMode",
    "ScrollPhase", "FrameShape", "Shadow", "TimerType", "ConnectionType",
    "CaseSensitivity", "SortOrder", "MatchFlag", "TextFormat", "TextFlag",
    "WindowModality", "InputMethodHint", "ScreenOrientation", "ShortcutContext",
    "ApplicationAttribute", "WindowFlags", "ItemFlag", "DockWidgetArea",
    "ToolBarArea", "ButtonRole", "DialogCode", "StandardButton",
    "MessageBoxIcon", "IconMode",
]

# 需要特殊处理的 API 差异
API_FIXES = [
    # PySide6: QFont.setFamilies / PySide2 无 setFamilies（用 setFamily）
    (r"\.setFamilies\(", ".setFamily("),
    # PySide6 的 exec 系列全部改成 exec_（PySide2 只提供带下划线的版本）
    (r"\bapp\.exec\(\)", "app.exec_()"),
    (r"\bm\.exec\(", "m.exec_("),
    (r"\bmenu\.exec\(", "menu.exec_("),
    (r"\bdialog\.exec\(", "dialog.exec_("),
    (r"\bd\.exec\(", "d.exec_("),

    # ---- QMouseEvent / QHoverEvent 坐标 API（Qt6 新增，Qt5 无）----
    # Qt6: ev.position() -> QPointF；Qt5: ev.pos() -> QPoint
    # 因 Qt5 返回 QPoint，紧随其后的 .toPoint() 也要一并去掉
    (r"\.position\(\)\.toPoint\(\)", ".pos()"),
    (r"\.globalPosition\(\)\.toPoint\(\)", ".globalPos()"),
    (r"\.scenePosition\(\)\.toPoint\(\)", ".scenePos()"),
    # 单独出现（未接 .toPoint()）的情况，放在后面兜底
    (r"\.position\(\)", ".pos()"),
    (r"\.globalPosition\(\)", ".globalPos()"),
    (r"\.scenePosition\(\)", ".scenePos()"),
]

# Qt6-only 的写法若漏改，运行时会抛 AttributeError，这里做静态兜底检查
QT6_ONLY_PATTERNS = [
    (r"\.position\(\)", "QMouseEvent.position() 是 Qt6 API，Qt5 用 .pos()"),
    (r"\.globalPosition\(\)", "QMouseEvent.globalPosition() 是 Qt6 API，Qt5 用 .globalPos()"),
    (r"\.scenePosition\(\)", "QMouseEvent.scenePosition() 是 Qt6 API，Qt5 用 .scenePos()"),
    (r"\.setFamilies\(", "QFont.setFamilies() 是 Qt6 API，Qt5 用 .setFamily()"),
]

# ---- 类的模块归属迁移（PySide6 → PySide2）----
# 同一批类在两个版本里所在的模块不同，必须调整 import 语句。
# 实测确认（PySide2 5.15.2.1，逐个 importlib.hasattr 验证）：
CLASS_MODULE_MOVES = {
    "QShortcut": ("QtGui", "QtWidgets"),
    "QAction": ("QtGui", "QtWidgets"),
}

# 从 QtGui 导入但 PySide2 里属于 QtWidgets 的类
GUI_TO_WIDGETS = ["QShortcut", "QAction"]
# 从 QtGui 导入但 PySide2 里属于 QtCore 的类
GUI_TO_CORE = ["QBuffer", "QByteArray", "QDataStream", "QTextStream"]
# 从 QtWidgets 导入但 PySide2 里属于 QtGui 的类
# （实测：QGraphicsOpacityEffect/QGraphicsEffect 在两版里都属于 QtWidgets，
#   不属于此列表，切勿误加）
WIDGETS_TO_GUI = []
# 从 QtCore 导入但 PySide2 里属于 QtGui 的类（源码里已在 QtGui，此表留空作兜底）
CORE_TO_GUI = []
# 从 QtCore 导入但 PySide2 里属于 QtWidgets 的类（源码里已在 QtWidgets，留空）
CORE_TO_WIDGETS = []


def convert(text: str, fname: str) -> tuple:
    """返回 (转换后文本, 变更计数列表)。

    重要发现：PySide2 5.15 已经支持类级枚举（PEP 435 风格），
    即 `Qt.WindowType.Window`、`QEvent.Type.MouseMove`、`QPainter.RenderHint.Antialiasing`
    在 PySide2 中同样可用。因此**不需要做枚举剥离**，只替换导入即可。
    这样转换风险最低，源码可读性也保持一致。
    """
    changes = []

    # ---- 1. 导入替换（唯一必需的改动）----
    n = len(re.findall(r"\bPySide6\b", text))
    text = text.replace("PySide6", "PySide2")
    if n:
        changes.append(f"导入 PySide6→PySide2: {n} 处")

    # ---- 2. import 语句：处理类归属变化 ----
    # 形如：from PySide2.QtGui import (QColor, QFont, QShortcut, ...)
    # PySide2 里 QShortcut 在 QtWidgets，需要从 QtGui 的导入列表中移出，
    # 并追加一条 from PySide2.QtWidgets import QShortcut
    text, moved = _fix_moved_imports(text)
    if moved:
        changes.append(f"类模块归属调整: {moved}")

    # ---- 3. API 差异修正 ----
    for pat, rep in API_FIXES:
        text, cnt = re.subn(pat, rep, text)
        if cnt:
            changes.append(f"API 修正 {pat}: {cnt} 处")

    return text, changes


def _parse_import_names(name_part: str) -> list:
    """把 'A, B, C' 或 '(A, B,\n  C)' 解析成符号列表。"""
    cleaned = name_part.strip()
    if cleaned.startswith("("):
        cleaned = cleaned[1:]
    if cleaned.endswith(")"):
        cleaned = cleaned[:-1]
    names = []
    for part in cleaned.split(","):
        tok = part.strip()
        if not tok:
            continue
        # 处理 as 别名
        names.append(tok.split()[0] if " as " in tok else tok)
    return names


def _fix_moved_imports(text: str) -> tuple:
    """把符号改到 PySide2 里正确的模块（支持任意方向的模块搬迁）。"""
    moved_count = 0

    # 每条规则：(源模块, 目标模块, 符号列表)
    RULES = [
        ("QtGui", "QtWidgets", GUI_TO_WIDGETS),
        ("QtGui", "QtCore", GUI_TO_CORE),
        ("QtWidgets", "QtGui", WIDGETS_TO_GUI),
        ("QtCore", "QtGui", CORE_TO_GUI),
        ("QtCore", "QtWidgets", CORE_TO_WIDGETS),
    ]

    # 收集所有需要追加的导入：目标模块 -> 符号集合
    to_add = {}

    for src_mod, dst_mod, symbols in RULES:
        if not symbols:
            continue
        pat = re.compile(
            r"from PySide2\." + src_mod + r" import (\([^)]*\)|[^\n(]+)",
            re.S,
        )

        def make_repl(src_mod, dst_mod, symbols, to_add):
            sym_set = set(symbols)

            def repl(m):
                names = _parse_import_names(m.group(1))
                stay = [n for n in names if n not in sym_set]
                gone = [n for n in names if n in sym_set]
                if gone:
                    to_add.setdefault(dst_mod, set()).update(gone)
                if not stay:
                    return ""          # 整条 import 全部搬走
                if len(stay) <= 3:
                    return f"from PySide2.{src_mod} import " + ", ".join(stay)
                body = ",\n    ".join(stay)
                return f"from PySide2.{src_mod} import (\n    " + body + ",\n)"
            return repl

        text, cnt = pat.subn(
            make_repl(src_mod, dst_mod, symbols, to_add), text)
        # subn 的 cnt 是替换次数，用 to_add 实际增量算搬家数更准

    moved_count = sum(len(v) for v in to_add.values())

    if to_add:
        lines = [ln for ln in text.split("\n") if ln.strip()]
        ins_at = 0
        for i, ln in enumerate(lines):
            if re.match(r"^(from|import)\s+\S", ln):
                ins_at = i + 1
                while ins_at < len(lines) and re.match(r"^\s+\S", lines[ins_at]):
                    ins_at += 1
        adds = [f"from PySide2.{mod} import " + ", ".join(sorted(syms))
                for mod, syms in sorted(to_add.items())]
        for ins in reversed(adds):
            lines.insert(ins_at, ins)
        text = "\n".join(lines)

    return text, moved_count


def convert_strict(text: str, fname: str) -> tuple:
    """严格模式：额外做枚举剥离（仅当 PySide2 不支持类级枚举时需要）。"""
    changes = []
    n = len(re.findall(r"\bPySide6\b", text))
    text = text.replace("PySide6", "PySide2")
    if n:
        changes.append(f"导入替换: {n} 处")

    total_enum = 0
    for scope in QT_SCOPES:
        pat = re.compile(r"\bQt\." + scope + r"\.([A-Za-z_][A-Za-z0-9_]*)")
        text, cnt = pat.subn(r"Qt.\1", text)
        total_enum += cnt
    if total_enum:
        changes.append(f"枚举剥离: {total_enum} 处")
    return text, changes


def main():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"源目录: {SRC_DIR}")
    print(f"输出目录: {OUT_DIR}\n")

    all_changes = {}
    for m in MODULES:
        src = os.path.join(SRC_DIR, m)
        if not os.path.exists(src):
            print(f"  跳过（不存在）: {m}")
            continue
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        new_text, changes = convert(text, m)
        dst = os.path.join(OUT_DIR, m)
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        if changes:
            all_changes[m] = changes
            print(f"  {m}: {'; '.join(changes)}")
        else:
            print(f"  {m}: 无变更")

    # 复制非 Python 资源
    for extra in ["app.ico"]:
        s = os.path.join(SRC_DIR, extra)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(OUT_DIR, extra))
            print(f"  复制资源: {extra}")

    print("\n=== 汇总 ===")
    print(f"处理模块: {len(MODULES)}")
    print(f"有变更模块: {len(all_changes)}")

    # 校验：输出里不应再有 PySide6；枚举保留是预期行为（PySide2 5.15 支持类级枚举）
    print("\n=== 校验 ===")
    issues = 0
    enum_kept = 0
    for m in MODULES:
        dst = os.path.join(OUT_DIR, m)
        if not os.path.exists(dst):
            continue
        t = open(dst, encoding="utf-8").read()
        if "PySide6" in t:
            print(f"  ❌ {m} 仍有 PySide6 导入")
            issues += 1
        for scope in QT_SCOPES:
            if f"Qt.{scope}." in t:
                enum_kept += 1
                break

    # 静态兜底：扫 Qt6-only API 是否残留
    print("\n=== Qt6-only API 兜底扫描 ===")
    for m in MODULES:
        dst = os.path.join(OUT_DIR, m)
        if not os.path.exists(dst):
            continue
        t = open(dst, encoding="utf-8").read()
        for pat, desc in QT6_ONLY_PATTERNS:
            hits = re.findall(pat, t)
            if hits:
                print(f"  ❌ {m}: 残留 {len(hits)} 处 —— {desc}")
                issues += 1

    if not issues:
        print("  ✅ 无 PySide6 残留，无 Qt6-only API 残留")
    print(f"  保留类级枚举的模块: {enum_kept} 个（PySide2 5.15 支持，正常）")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
