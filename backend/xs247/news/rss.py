"""Đọc RSS/Atom của báo: chỉ lấy tiêu đề, tóm tắt ngắn và liên kết gốc (không sao chép toàn văn)."""
from __future__ import annotations

import inspect
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..config import VN_TZ
from ..sources.html_util import strip_tags
from .filter import is_clean

MAX_BYTES = 2_000_000
SUMMARY_MAX = 300
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?$")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _text(el, *names: str) -> str:
    for c in el:
        if _local(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return ""


def _clean(s: str) -> str:
    return strip_tags(s).strip()


def _short(s: str) -> str:
    return s if len(s) <= SUMMARY_MAX else s[:SUMMARY_MAX - 1].rstrip() + "…"


def parse_date(s: str | None) -> datetime | None:
    """RFC-822 (kể cả năm 2 chữ số), ISO-8601 (Atom) hoặc "MM/DD/YYYY h:mm:ss AM" (Tuổi Trẻ); không rõ múi giờ = giờ Việt Nam."""
    s = (s or "").strip()
    if not s:
        return None
    dt = None
    m = _US_DATE.match(s)
    try:
        if m:
            mo, d, y, h, mi, sec, ap = m.groups()
            h = int(h)
            if ap:
                h = h % 12 + (12 if ap.lower() == "pm" else 0)
            dt = datetime(int(y), int(mo), int(d), h, int(mi), int(sec or 0))
        else:
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                dt = parsedate_to_datetime(s)
    except (ValueError, TypeError, OverflowError, IndexError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)


def _link(el) -> str:
    for c in el:
        if _local(c.tag) != "link":
            continue
        href = c.get("href")
        if href and c.get("rel", "alternate") == "alternate":
            return href.strip()
        if (c.text or "").strip():
            return c.text.strip()
    for c in el:  # Atom chỉ có link không rel
        if _local(c.tag) == "link" and c.get("href"):
            return c.get("href").strip()
    return ""


def parse_feed(xml_text: str, source_name: str) -> list[dict]:
    head = xml_text.upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise ValueError("Nguồn tin chứa khai báo DOCTYPE/ENTITY, từ chối đọc")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"RSS không hợp lệ: {e}") from e
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _clean(_text(el, "title"))
        url = _link(el)
        if not title or not url:
            continue
        summary = _short(_clean(_text(el, "description", "summary", "content")))
        pub = parse_date(_text(el, "pubdate", "published", "updated", "date"))
        out.append({"title": title, "url": url, "summary": summary, "source_name": source_name, "published_at": pub})
    return out


def select_items(items: list[dict], pattern: str | None) -> list[dict]:
    rx = re.compile(pattern, re.IGNORECASE) if pattern else None
    out = []
    for it in items:
        if not (is_clean(it["title"]) and is_clean(it["summary"])):
            continue
        if rx and not rx.search(f"{it['title']} {it['summary']}"):
            continue
        out.append(it)
    return out


async def fetch_feed(http, feed: dict, robots_allowed=None) -> list[dict]:
    url = feed["url"]
    if robots_allowed is not None:
        ok = robots_allowed(url)
        if inspect.isawaitable(ok):
            ok = await ok
        if not ok:
            return []
    r = await http.get(url)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    if len(r.text) > MAX_BYTES:
        raise ValueError("Nguồn tin quá lớn")
    return select_items(parse_feed(r.text, feed["name"]), feed.get("include_pattern"))
