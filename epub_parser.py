# -*- coding: utf-8 -*-
"""EPUB 解析引擎：支持 EPUB 2 / EPUB 3，抽取目录与章节纯文本。"""
from __future__ import annotations

import os
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from html import unescape

__all__ = ["EpubBook", "TxtBook", "Chapter", "open_epub", "open_book"]


@dataclass
class Chapter:
    """单章数据。"""
    index: int
    title: str
    href: str            # 相对 OPF 的路径，用于去重与排序
    paragraphs: list = field(default_factory=list)


# ---------------------------------------------------------------- 工具函数

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_PARA_RE = re.compile(r"<(p|div|h1|h2|h3|h4|h5|h6|li)\b[^>]*>(.*?)</\1>", re.I | re.S)


def _strip_tags(fragment: str) -> str:
    """去掉标签并还原实体，保留必要的换行。"""
    fragment = _BR_RE.sub("\n", fragment)
    fragment = _TAG_RE.sub("", fragment)
    text = unescape(fragment)
    # 压缩空白，但保留段落内的单个换行
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _extract_paragraphs(html: str) -> list:
    """从 XHTML 抽取段落列表。"""
    body = html
    m = re.search(r"<body\b[^>]*>(.*?)</body>", html, re.I | re.S)
    if m:
        body = m.group(1)
    body = _SCRIPT_RE.sub("", body)

    paras = []
    for _tag, inner in _PARA_RE.findall(body):
        text = _strip_tags(inner)
        if text:
            paras.append(text)

    if not paras:
        # 兜底：没有块级标签时按换行切
        text = _strip_tags(body)
        paras = [p.strip() for p in text.split("\n") if p.strip()]
    return paras


def _clean_title(raw: str) -> str:
    """清理章节标题，去掉 EPUB 自带的换行与多余空白。"""
    t = re.sub(r"\s+", " ", raw or "").strip()
    return t


# ---------------------------------------------------------------- 主类

class EpubBook:
    """一个已打开的 EPUB 书籍。"""

    def __init__(self, path: str):
        self.path = path
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.author = ""
        self.cover_href = ""
        self.toc: list = []          # [(title, opf_relative_href)]
        self._opf_dir = ""
        self._spine: list = []       # opf 相对路径，按阅读顺序
        self._html_cache: dict = {}  # href -> paragraphs
        self._zip = zipfile.ZipFile(path)
        self._parse()

    # ------------------------------------------------------------ 解析

    def _read(self, name: str) -> str:
        try:
            data = self._zip.read(name)
        except KeyError:
            return ""
        for enc in ("utf-8", "gb18030", "utf-16"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    def _parse(self):
        container = self._read("META-INF/container.xml")
        m = re.search(r'full-path\s*=\s*"([^"]+)"', container)
        opf_path = m.group(1) if m else "OEBPS/content.opf"
        self._opf_dir = posixpath.dirname(opf_path)

        opf = self._read(opf_path)
        if not opf:
            raise ValueError("无法读取 EPUB 的 OPF 清单文件")

        # --- 元数据
        m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.I | re.S)
        if m:
            self.title = _strip_tags(m.group(1)) or self.title
        m = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.I | re.S)
        if m:
            self.author = _strip_tags(m.group(1))

        # --- manifest: id -> href
        id2href = {}
        for item in re.finditer(r"<item\b([^>]*)/?>", opf, re.I):
            attrs = item.group(1)
            iid = re.search(r'id\s*=\s*"([^"]+)"', attrs)
            href = re.search(r'href\s*=\s*"([^"]+)"', attrs)
            mt = re.search(r'media-type\s*=\s*"([^"]+)"', attrs)
            if iid and href:
                id2href[iid.group(1)] = (href.group(1), mt.group(1) if mt else "")
        for iid, (href, mt) in id2href.items():
            if "image" in mt and ("cover" in iid.lower() or "cover" in href.lower()):
                self.cover_href = href
                break
        m = re.search(r'name\s*=\s*"cover"\s+content\s*=\s*"([^"]+)"', opf, re.I)
        if m and m.group(1) in id2href:
            self.cover_href = id2href[m.group(1)][0]

        # --- spine: 阅读顺序
        for ref in re.finditer(r"<itemref\b([^>]*)/?>", opf, re.I):
            rid = re.search(r'idref\s*=\s*"([^"]+)"', ref.group(1))
            if rid and rid.group(1) in id2href:
                self._spine.append(id2href[rid.group(1)][0])

        # 兜底：spine 缺失时按文件名自然排序
        if not self._spine:
            files = [h for i, (h, mt) in id2href.items() if "html" in mt or h.endswith((".html", ".xhtml"))]
            self._spine = sorted(files, key=self._natural_key)

        # --- NCX / nav 目录
        self.toc = self._parse_ncx(opf, id2href) or self._parse_nav(opf, id2href)

        # --- 目录兜底：用正文自身生成的标题
        if not self.toc:
            self.toc = [(f"第 {i + 1} 节", h) for i, h in enumerate(self._spine) if not self._is_noise(h)]

    @staticmethod
    def _natural_key(href: str):
        parts = re.split(r"(\d+)", href)
        return [int(p) if p.isdigit() else p.lower() for p in parts]

    @staticmethod
    def _is_noise(href: str) -> bool:
        low = href.lower()
        return any(k in low for k in ("cover", "copyright", "instruction", "toc", "nav", "titlepage"))

    def _parse_ncx(self, opf: str, id2href: dict) -> list:
        ncx_href = ""
        for iid, (href, mt) in id2href.items():
            if "dtbncx" in mt or href.lower().endswith(".ncx"):
                ncx_href = href
                break
        if not ncx_href:
            return []
        base = posixpath.normpath(posixpath.join(self._opf_dir, ncx_href))
        ncx = self._read(base)
        if not ncx:
            return []
        ncx_dir = posixpath.dirname(base)

        out = []
        for pt in re.finditer(r"<navPoint\b.*?</navPoint>", ncx, re.I | re.S):
            block = pt.group(0)
            t = re.search(r"<text[^>]*>(.*?)</text>", block, re.I | re.S)
            s = re.search(r'<content\b[^>]*src\s*=\s*"([^"]+)"', block, re.I)
            if not (t and s):
                continue
            title = _clean_title(_strip_tags(t.group(1)))
            src = s.group(1).split("#")[0]
            href = posixpath.normpath(posixpath.join(ncx_dir, src))
            if "/Text/" in href or True:
                out.append((title, os.path.relpath(href, self._opf_dir).replace("\\", "/")))
        return out

    def _parse_nav(self, opf: str, id2href: dict) -> list:
        nav_href = ""
        for iid, (href, mt) in id2href.items():
            if iid.lower() in ("nav", "toc") or "nav" in href.lower():
                nav_href = href
                break
        if not nav_href:
            return []
        base = posixpath.normpath(posixpath.join(self._opf_dir, nav_href))
        nav = self._read(base)
        nav_dir = posixpath.dirname(base)
        out = []
        for a in re.finditer(r'<a\b[^>]*href\s*=\s*"([^"]+)"[^>]*>(.*?)</a>', nav, re.I | re.S):
            title = _clean_title(_strip_tags(a.group(2)))
            href = posixpath.normpath(posixpath.join(nav_dir, a.group(1).split("#")[0]))
            if title:
                out.append((title, os.path.relpath(href, self._opf_dir).replace("\\", "/")))
        return out

    # ------------------------------------------------------------ 对外接口

    @property
    def chapter_count(self) -> int:
        return len(self.toc)

    def chapter_href(self, index: int) -> str:
        return self.toc[index][1]

    def chapter_title(self, index: int) -> str:
        return self.toc[index][0]

    def chapter_paragraphs(self, index: int) -> list:
        """返回第 index 章的段落列表（带缓存）。"""
        href = self.chapter_href(index)
        if href in self._html_cache:
            return self._html_cache[href]
        full = posixpath.normpath(posixpath.join(self._opf_dir, href))
        html = self._read(full)
        paras = _extract_paragraphs(html)
        # 章节首段若是标题，去掉，避免与导航标题重复
        if paras and self._similar(paras[0], self.chapter_title(index)):
            paras = paras[1:]
        self._html_cache[href] = paras
        return paras

    def cover_bytes(self):
        if not self.cover_href:
            return None
        full = posixpath.normpath(posixpath.join(self._opf_dir, self.cover_href))
        try:
            return self._zip.read(full)
        except KeyError:
            return None

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        na = re.sub(r"[\s第章章节0-9０-９\.、]", "", a)
        nb = re.sub(r"[\s第章章节0-9０-９\.、]", "", b)
        if not na or not nb:
            return False
        return na in nb or nb in na

    def search(self, keyword: str, limit: int = 300) -> list:
        """全文搜索，返回 [(章节序号, 章节名, 片段)]。"""
        keyword = keyword.strip()
        if not keyword:
            return []
        hits = []
        for i in range(self.chapter_count):
            for p in self.chapter_paragraphs(i):
                if keyword in p:
                    pos = p.find(keyword)
                    start = max(0, pos - 28)
                    snip = ("…" if start else "") + p[start:pos + len(keyword) + 34] + "…"
                    hits.append((i, self.chapter_title(i), snip))
                    break  # 每章最多一条，避免结果爆炸
            if len(hits) >= limit:
                break
        return hits

    def close(self):
        try:
            self._zip.close()
        except Exception:
            pass


def open_epub(path: str) -> EpubBook:
    return EpubBook(path)


# ---------------------------------------------------------------- TXT 支持

class TxtBook:
    """把纯文本小说包装成与 EpubBook 相同的接口。

    自动识别「第X章 / Chapter N」式标题进行分章；识别不到时按字数切块。
    """

    _CHAPTER_RE = re.compile(
        r"^[ \t　]*("
        r"第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*[章节回卷篇节][^\n]{0,40}"
        r"|[Cc]hapter\s+[0-9]+[^\n]{0,40}"
        r"|[0-9]{1,4}\s*[、.．][^\n]{0,40}"
        r")[ \t　]*$",
        re.M)

    def __init__(self, path: str, chunk_size: int = 3000):
        self.path = path
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.author = ""
        self.cover_href = ""
        self.chapters: list = []
        self.toc: list = []
        self._load(chunk_size)

    def _decode(self, data: bytes) -> str:
        for enc in ("utf-8", "gb18030", "utf-16", "big5"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    def _load(self, chunk_size: int):
        with open(self.path, "rb") as f:
            raw = self._decode(f.read())
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")

        marks = [(m.start(), m.group(1).strip()) for m in self._CHAPTER_RE.finditer(raw)]

        if len(marks) >= 2:
            for i, (pos, title) in enumerate(marks):
                end = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
                body = raw[pos + len(title):end]
                paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
                if len(paras) <= 1:
                    paras = [p.strip() for p in body.split("\n") if p.strip()]
                self.chapters.append(Chapter(i, _clean_title(title), f"__txt__{i}", paras))
        else:
            for i in range(0, len(raw), chunk_size):
                blk = raw[i:i + chunk_size]
                paras = [p.strip() for p in blk.split("\n") if p.strip()]
                self.chapters.append(Chapter(len(self.chapters), f"第 {len(self.chapters) + 1} 部分",
                                             f"__txt__{len(self.chapters)}", paras))

        self.toc = [(c.title, c.href) for c in self.chapters]

    # ---- 与 EpubBook 一致的接口
    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    def chapter_href(self, index: int) -> str:
        return self.chapters[index].href

    def chapter_title(self, index: int) -> str:
        return self.chapters[index].title

    def chapter_paragraphs(self, index: int) -> list:
        return self.chapters[index].paragraphs

    def cover_bytes(self):
        return None

    def search(self, keyword: str, limit: int = 300) -> list:
        keyword = keyword.strip()
        if not keyword:
            return []
        hits = []
        for c in self.chapters:
            for p in c.paragraphs:
                if keyword in p:
                    pos = p.find(keyword)
                    start = max(0, pos - 28)
                    hits.append((c.index, c.title,
                                 ("…" if start else "") + p[start:pos + len(keyword) + 34] + "…"))
                    break
            if len(hits) >= limit:
                break
        return hits

    def close(self):
        pass


def open_book(path: str):
    """按扩展名选择解析器。"""
    if path.lower().endswith(".txt"):
        return TxtBook(path)
    return EpubBook(path)

