# -*- coding: utf-8 -*-
"""生成应用图标 app.ico（多尺寸）。用 Qt 绘制，无需外部依赖。"""
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QBrush

SIZES = [256, 128, 64, 48, 32, 16]


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 256.0
    p.scale(s, s)

    # 圆角深色底
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(6, 6, 244, 244), 54, 54)
    p.fillPath(bg, QBrush(QColor("#26262E")))

    # 幽灵身体
    left, right = 64.0, 192.0
    top, bottom = 56.0, 196.0
    w = right - left
    seg = w / 3.0

    g = QPainterPath()
    g.moveTo(left, top + w / 2)              # 左上，半圆起点高度
    g.arcTo(QRectF(left, top, w, w), 180, -180)   # 顶部半圆
    g.lineTo(right, bottom)
    # 下摆三个凸弧
    g.quadTo(right - seg * 0.5, bottom + 22, right - seg, bottom)
    g.quadTo(right - seg * 1.5, bottom + 22, right - seg * 2, bottom)
    g.quadTo(right - seg * 2.5, bottom + 22, left, bottom)
    g.closeSubpath()
    p.fillPath(g, QBrush(QColor("#E8E8EE")))

    # 眼睛
    p.setBrush(QBrush(QColor("#26262E")))
    p.setPen(Qt.PenStyle.NoPen)
    for cx in (102.0, 154.0):
        p.drawEllipse(QRectF(cx - 12, 114 - 15, 24, 30))

    p.end()
    return img


def to_png(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def make_ico(images, sizes) -> bytes:
    """手写 ICO 容器（内嵌 PNG），兼容 Vista+。"""
    pngs = [to_png(im) for im in images]
    n = len(pngs)
    header = struct.pack("<HHH", 0, 1, n)
    entries = b""
    offset = 6 + 16 * n
    blob = b""
    for png, sz in zip(pngs, sizes):
        d = 0 if sz >= 256 else sz
        entries += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blob += png
    return header + entries + blob


imgs = []
for sz in SIZES:
    imgs.append(draw(sz))

ico = make_ico(imgs, SIZES)
open("app.ico", "wb").write(ico)
print(f"app.ico 已生成: {len(ico)} 字节, 尺寸 {SIZES}")

# 顺便存一张 PNG 预览（不进仓库）
draw(256).save("_icon_preview.png", "PNG")
print("预览图: _icon_preview.png")
