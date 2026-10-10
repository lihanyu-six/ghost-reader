# 第三方组件许可声明

本软件（幽灵阅读器 / Ghost Reader）在运行时使用了以下第三方组件。
本项目未修改这些组件的源代码，均以**动态链接**方式使用。

---

## 1. PySide6 (Qt for Python)

- 版本：6.12.0
- 主页：https://www.qt.io/qt-for-python
- 许可证：**LGPL-3.0-only**（亦提供 GPL-2.0-only / GPL-3.0-only 双授权选项）
- 本项目选择遵循 **LGPL-3.0** 条款使用

### 许可全文

LGPL-3.0 全文见：https://www.gnu.org/licenses/lgpl-3.0.html

LGPL-3.0 附加条款（来自 GPL-3.0 第 7 节）：https://www.gnu.org/licenses/gpl-3.0.html

### LGPL-3.0 合规说明

本软件以单文件可执行程序分发，PySide6 / Qt 以动态库形式被链接。

依据 LGPL-3.0 第 4 条（Combined Works）与第 6 条（Combined Libraries），
我们在此提供以下说明，以便你行使 LGPL 赋予的权利：

1. **获取库源码**：PySide6 的完整源码可从 https://code.qt.io/cgit/pyside/pyside-setup.git/
   获取。PyPI 上发布的对应版本包（含二进制）可从 https://pypi.org/project/PySide6/6.12.0/ 下载。
2. **替换库文件**：本程序打包后的 Qt 动态库（`PySide6/*.pyd`、`Qt6*.dll`、`shiboken6*` 等）
   位于运行时解包目录中。你可以用自行编译或从 PyPI 获取的同版本库文件替换它们，
   以验证修改后的库能够与本程序协同工作。
3. **无附加限制**：本项目未对上述库施加任何超出 LGPL-3.0 的附加限制。

---

## 2. Qt 6

PySide6 基于 Qt 6，同样采用 LGPL-3.0 许可。

- 主页：https://www.qt.io/
- 许可全文：https://www.gnu.org/licenses/lgpl-3.0.html

---

## 3. PySide2 (Qt for Python) —— 仅 Windows 7 兼容版

- 版本：5.15.2.1
- 主页：https://www.qt.io/qt-for-python
- 许可证：**LGPL-3.0-only**（亦提供 GPL-2.0-only / GPL-3.0-only 双授权选项）
- 本项目选择遵循 **LGPL-3.0** 条款使用

### 用途说明

仅 `GhostReader-Setup-Win7-*.exe`（Windows 7 兼容版）使用 PySide2，
因为 Qt 6 要求 Windows 10 及以上，而 **Qt 5.15 是最后一个支持 Windows 7 的版本**。
Windows 10 / 11 版仍使用 PySide6。

### 许可全文

LGPL-3.0 全文见：https://www.gnu.org/licenses/lgpl-3.0.html

### LGPL-3.0 合规说明

与 PySide6 相同：以单文件可执行程序分发，Qt 动态库以动态链接方式使用，
未修改其源码。你可从 https://pypi.org/project/PySide2/5.15.2.1/ 获取同版本原始库文件，
并用其替换打包产物中的 Qt5 动态库（`PySide2/*.pyd`、`Qt5*.dll`、`shiboken2*` 等）。
本项目未对其施加任何超出 LGPL-3.0 的附加限制。

---

## 4. Qt 5

PySide2 基于 Qt 5，同样采用 LGPL-3.0 许可。

- 主页：https://www.qt.io/
- 许可全文：https://www.gnu.org/licenses/lgpl-3.0.html

---

## 5. Python 标准库

- 版本：3.13（Win10/11 版）/ 3.8（Win7 兼容版）
- 许可证：**PSF-2.0**（Python Software Foundation License）
- 许可全文：https://docs.python.org/3/license.html
- 说明：Python 标准库许可允许自由分发，无附加限制。

---

## 6. Inno Setup 简体中文语言包

- 文件：`ChineseSimplified.isl`
- 用途：构建安装包时提供中文安装界面（**不随软件二进制分发**）
- 来源：Inno Setup 官方社区翻译 <https://jrsoftware.org/files/istrans/>
- 维护者：Zhenghan Yang (Kira)
- 说明：该翻译文件按 Inno Setup 的惯例自由分发，随本项目仓库一同提供仅为便于复现构建。

---

## 7. 本项目自身

本项目源代码采用 **MIT License**，详见 [LICENSE](LICENSE)。

---

## 版权声明

"Qt" 与 "PySide" 是 The Qt Company Ltd. 的商标。
"Inno Setup" 是 Jordan Russell 的商标。
本项目的名称与标识不包含、也不主张任何上述商标权利。
