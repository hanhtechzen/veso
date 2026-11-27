"""Tìm kiếm thông minh: hiểu câu gõ tự nhiên như 'xsmn 26/10', 'lô 27 tp hcm', 'power kỳ 1417', 'vé 472899'."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..domain.games import GAMES


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").replace("Đ", "D").replace("đ", "d"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9*/\-.\s]", " ", t)).strip()


REGION_WORDS = [("mb", r"\b(xsmb|kqxsmb|sxmb|xstd|xshn|mien bac|ha noi|thu do)\b"),
                ("mn", r"\b(xsmn|kqxsmn|sxmn|mien nam)\b"),
                ("mt", r"\b(xsmt|kqxsmt|sxmt|mien trung)\b")]
GAME_WORDS = [("max3dpro", r"\b(max ?3d ?pro|3d ?pro)\b"), ("max3d", r"\b(max ?3d|3d)\b"),
              ("power655", r"\b(power|6/55|655|p655)\b"), ("mega645", r"\b(mega|6/45|645)\b"),
              ("lotto535", r"\b(lotto|5/35|535)\b"), ("keno", r"\bkeno\b"), ("bingo18", r"\bbingo(18)?\b"),
              ("tt4", r"\b(than tai|tt4|thantai)\b"), ("dt6x36", r"\b6x36\b"), ("dt123", r"(1\*2\*3|\b123\b|dien toan 123)")]
WEEKDAYS = {"thu 2": 0, "thu hai": 0, "t2": 0, "thu 3": 1, "thu ba": 1, "t3": 1, "thu 4": 2, "thu tu": 2, "t4": 2,
            "thu 5": 3, "thu nam": 3, "t5": 3, "thu 6": 4, "thu sau": 4, "t6": 4, "thu 7": 5, "thu bay": 5, "t7": 5,
            "chu nhat": 6, "cn": 6}
PROVINCE_ALIASES = {"tp-hcm": ["hcm", "tphcm", "tp hcm", "ho chi minh", "sai gon", "saigon", "xshcm"],
                    "thua-thien-hue": ["hue", "xshue", "tth"], "vung-tau": ["vt", "ba ria", "xsvt"], "da-lat": ["lam dong", "xsdl"],
                    "da-nang": ["xsdng", "dng"], "khanh-hoa": ["nha trang", "xskh"], "can-tho": ["xsct"], "dong-thap": ["xsdt"]}


@dataclass
class Intent:
    region: str | None = None
    province: str | None = None
    game: str | None = None
    day: date | None = None
    seq: int | None = None
    lo: list[str] = field(default_factory=list)
    tickets: list[str] = field(default_factory=list)
    topic: str | None = None   # thong-ke | so-ket-qua | lich-quay


def parse(q: str, provinces: list[dict], today: date) -> Intent:
    t = " " + norm(q) + " "
    it = Intent()
    for code, pat in GAME_WORDS:
        if re.search(pat, t):
            it.game = code
            t = re.sub(pat, " ", t)
            break
    for code, pat in REGION_WORDS:
        if re.search(pat, t):
            it.region = code
            t = re.sub(pat, " ", t)
            break
    # tỉnh: so khớp tên không dấu, bỏ khoảng trắng, kèm tên gọi tắt quen thuộc
    compact = t.replace(" ", "")
    best = None
    for p in provinces:
        names = [norm(p["name"]).replace("tp. ", "").replace(" ", "")] + [a.replace(" ", "") for a in PROVINCE_ALIASES.get(p["code"], [])]
        for nm in names:
            if len(nm) >= 3 and nm in compact and (best is None or len(nm) > best[1]):
                best = (p, len(nm))
    if best and not it.game:
        it.province, it.region = best[0]["code"], best[0]["region_code"]
    # thời gian
    if re.search(r"\bhom nay\b", t):
        it.day = today
    elif re.search(r"\bhom qua\b", t):
        it.day = today - timedelta(days=1)
    elif re.search(r"\bhom kia\b", t):
        it.day = today - timedelta(days=2)
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", t)
    if m and not (it.game in ("power655", "mega645", "lotto535") and m.group(0) in ("6/55", "6/45", "5/35")):
        d_, mo = int(m[1]), int(m[2])
        y = int(m[3]) if m[3] else today.year
        y = y + 2000 if y < 100 else y
        try:
            cand = date(y, mo, d_)
            if not m[3] and cand > today:
                cand = date(y - 1, mo, d_)
            it.day = cand
        except ValueError:
            pass
        t = t.replace(m.group(0), " ")
    for k, wd in sorted(WEEKDAYS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{k}\b", t):
            if not it.day:
                it.day = today - timedelta(days=(today.weekday() - wd) % 7)
            t = re.sub(rf"\b{k}\b", " ", t)
            break
    m = re.search(r"\bky\s*#?\s*(\d{3,7})\b", t)
    if m:
        it.seq = int(m[1])
        t = t.replace(m.group(0), " ")
    if re.search(r"\b(lo gan|thong ke|tan suat|gan)\b", t):
        it.topic = "thong-ke"
    elif re.search(r"\b(so ket qua|so \d+ ngay)\b", t):
        it.topic = "so-ket-qua"
    elif re.search(r"\b(lich quay|lich mo thuong|gio quay|may gio)\b", t):
        it.topic = "lich-quay"
    t = re.sub(r"\b(lo|de|so|ve|xo so|xs|kq|ket qua|tim|xem)\b", " ", t)
    for tok in re.findall(r"\b\d+\b", t):
        if it.game in GAMES and GAMES[it.game].kind == "pick" and len(tok) <= 2:
            it.lo.append(tok.zfill(2))
        elif len(tok) <= 2:
            it.lo.append(tok.zfill(2))
        elif len(tok) in (5, 6):
            it.tickets.append(tok)
    it.lo = list(dict.fromkeys(it.lo))[:4]
    return it
