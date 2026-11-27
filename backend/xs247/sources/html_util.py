"""Tiện ích đọc HTML không cần thư viện ngoài, và kiểm tra robots.txt."""
from __future__ import annotations

import html
import re
import time
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

_SCRIPT = re.compile(r"<(script|style)[\s\S]*?</\1>", re.I)
_TAG = re.compile(r"<[^>]+>")


def strip_tags(markup: str) -> str:
    """Bỏ thẻ, giải mã ký tự (&igrave; ...), gộp khoảng trắng, chuẩn hóa Unicode NFC."""
    text = _TAG.sub(" ", _SCRIPT.sub(" ", markup))
    text = html.unescape(text)
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text))


class ClassText(HTMLParser):
    """Gom nội dung chữ của các thẻ có class nằm trong danh sách cần tìm."""

    def __init__(self, classes: set[str]):
        super().__init__(convert_charrefs=True)
        self.classes = classes
        self.found: dict[str, list[str]] = {c: [] for c in classes}
        self._stack: list[tuple[str, str | None]] = []  # (tag, class đang gom)
        self._buf: dict[int, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        hit = next((c for c in cls.split() if c in self.classes), None)
        self._stack.append((tag, hit))
        if hit:
            self._buf[len(self._stack)] = []

    def handle_endtag(self, tag):
        while self._stack:
            depth = len(self._stack)
            t, hit = self._stack.pop()
            if hit:
                self.found[hit].append("".join(self._buf.pop(depth, [])).strip())
            if t == tag:
                break

    def handle_data(self, data):
        for depth in self._buf:
            self._buf[depth].append(data)


def by_class(markup: str, classes: set[str]) -> dict[str, list[str]]:
    p = ClassText(classes)
    p.feed(markup)
    p.close()
    return p.found


class SourceBlocked(Exception):
    """Nguồn không cho phép truy cập tự động (robots.txt hoặc chặn bot)."""


class Robots:
    """Kiểm tra robots.txt, lưu đệm 6 giờ cho mỗi tên miền."""

    TTL = 6 * 3600

    def __init__(self):
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def allowed(self, http: httpx.AsyncClient, url: str, agent: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        hit = self._cache.get(base)
        if not hit or time.monotonic() - hit[0] > self.TTL:
            rp: RobotFileParser | None = None
            try:
                r = await http.get(base + "/robots.txt", timeout=10)
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None  # không đọc được robots.txt thì coi như không có giới hạn
            hit = (time.monotonic(), rp)
            self._cache[base] = hit
        rp = hit[1]
        return True if rp is None else rp.can_fetch(agent, url)


ROBOTS = Robots()
