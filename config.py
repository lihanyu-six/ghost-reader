# -*- coding: utf-8 -*-
"""配置持久化 + 主题定义。"""
from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ghost_reader")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "opacity": 0.82,          # 窗口不透明度
    "chinese_font": "微软雅黑",
    "title_font": "宋体",
    "font_size": 17,
    "line_height": 185,       # 行距百分比
    "letter_spacing": 100,    # 字间距百分比
    "bg_color": "#1E1E20",
    "fg_color": "#C9C9CB",
    "paper_gamma": 0,
    "page_mode": "scroll",    # scroll | page
    "always_on_top": True,
    "auto_hide": False,
    "width": 560,
    "height": 760,
    "x": -1,
    "y": -1,
    "font_weight": 400,
    "text_protect": 0,        # 文字保护：0~100，越大文字越实、背景越透
    "bg_max_alpha": 100,      # 背景最高不透明度百分比
    "last_book": "",
    "last_chapter": 0,
    "recent_books": [],
    "hotkey_index": 0,
    "library_dir": "",
    "welcome_seen": False,
}

# 预设主题： (显示名, 背景色, 文字色, 是否浅色)
THEMES = [
    ("暗夜", "#1E1E20", "#C9C9CB", False),
    ("纯黑", "#000000", "#A8A8A8", False),
    ("护眼绿", "#CCE8CF", "#2B3A2E", True),
    ("羊皮纸", "#F5EDDC", "#3C3328", True),
    ("米白", "#FAF8F3", "#333333", True),
    ("蓝灰", "#2B3440", "#BFC9D4", False),
    ("裸透明", "#101012", "#D0D0D0", False),
]


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    self.data[k] = v
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value

    def push_recent(self, path: str):
        recents = [p for p in self.get("recent_books", []) if p != path]
        recents.insert(0, path)
        self.set("recent_books", recents[:12])
