# -*- coding: utf-8 -*-
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 5.13 打包配置 —— Windows 7 兼容版（PySide2 + Python 3.8）

与主 build.spec 的差异：
- 使用 PySide2（Qt 5.15）而非 PySide6（Qt 6）
- 排除 QtWebEngine / Qt3D 等大模块
- 生成到 dist_win7/
"""
import os

block_cipher = None

# 关键：以 win7_build 目录为工作目录，确保导入的是 PySide2 版源码
# （根目录下的 *.py 是 PySide6 版，绝不能被打进去）
BUILD_SRC = os.path.abspath("win7_build")

# 排除项：只排最占体积且确定用不到的（保守策略，避免干扰 PySide2 hook）
EXCLUDES = [
    # Qt 大模块（本项目只用 QtCore / QtGui / QtWidgets）
    "PySide2.QtWebEngineWidgets", "PySide2.QtWebEngineCore",
    "PySide2.QtWebEngine", "PySide2.QtWebKit", "PySide2.QtWebKitWidgets",
    "PySide2.Qt3DCore", "PySide2.Qt3DRender", "PySide2.Qt3DInput",
    "PySide2.Qt3DLogic", "PySide2.Qt3DAnimation", "PySide2.Qt3DExtras",
    "PySide2.QtCharts", "PySide2.QtDataVisualization", "PySide2.QtMultimedia",
    "PySide2.QtMultimediaWidgets", "PySide2.QtQuick", "PySide2.QtQuickWidgets",
    "PySide2.QtQml", "PySide2.QtSql", "PySide2.QtTest", "PySide2.QtDesigner",
    "PySide2.QtHelp", "PySide2.QtNfc", "PySide2.QtPositioning",
    "PySide2.QtScript", "PySide2.QtScriptTools", "PySide2.QtSensors",
    "PySide2.QtSerialPort", "PySide2.QtUiTools", "PySide2.QtXmlPatterns",
    "PySide2.QtLocation", "PySide2.QtRemoteObjects", "PySide2.QtScxml",
    "PySide2.QtTextToSpeech", "PySide2.QtBluetooth", "PySide2.QtOpenGL",
    "PySide2.QtPrintSupport", "PySide2.QtSvg", "PySide2.QtXml",
    # 其他无关库
    "tkinter", "unittest", "pydoc", "doctest", "difflib",
    "http.server", "xmlrpc", "pdb", "lib2to3", "test", "distutils",
    "setuptools", "pip", "wheel", "numpy", "matplotlib", "PIL",
    "IPython", "pytest",
]

a = Analysis(
    [os.path.join(BUILD_SRC, "main.py")],
    pathex=[BUILD_SRC],          # 只放 win7_build，避免误导入根目录的 PySide6 版
    binaries=[],
    datas=[(os.path.join(BUILD_SRC, "app.ico"), ".")],
    hiddenimports=["panels", "config", "epub_parser", "window_utils", "booklist"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="幽灵阅读器-Win7",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="app.ico",
)
