"""Bộ cào xoso.com.vn cho xổ số miền Bắc, miền Nam và miền Trung.

- Miền Bắc: https://xoso.com.vn/xsmb-<dd-mm-yyyy>.html, các số nằm trong thẻ có class special-prize,
  prize1 ... prize7 (theo dự án mã nguồn mở khiemdoan/vietnam-lottery-xsmb-analysis).
- Miền Nam, miền Trung: https://xoso.com.vn/xsmn-<dd-mm-yyyy>.html và xsmt-..., một bảng class
  "table-result": dòng đầu là tên các đài, mỗi dòng sau là một giải (8, 7, ... 1, ĐB), mỗi cột một đài
  (theo dự án mã nguồn mở aloha123890/vietnam-lottery).
Lưu ý: trang có thể bật chống bot; nếu bị chặn, bộ cào báo lỗi rõ ràng chứ không tìm cách vượt qua.
"""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

from .base import DrawRef, FetchResult, Parsed, ParseError
from .html_util import by_class
from .scrape_base import ScrapeAdapter

CLASS_TO_PRIZE = {"special-prize": "db", "prize1": "g1", "prize2": "g2", "prize3": "g3",
                  "prize4": "g4", "prize5": "g5", "prize6": "g6", "prize7": "g7"}
ROW_TO_PRIZE = {"8": "g8", "7": "g7", "6": "g6", "5": "g5", "4": "g4", "3": "g3", "2": "g2", "1": "g1",
                "db": "db", "dacbiet": "db"}
# Tên đài trên trang -> mã đài (viết liền, không dấu gạch) khi tên khác mã
ALIASES = {"hue": "thuathienhue", "hcm": "tphcm", "hochiminh": "tphcm", "tphochiminh": "tphcm",
           "lamdong": "dalat", "bariavungtau": "vungtau", "daclac": "daklak", "dacnong": "daknong"}


def key(text: str) -> str:
    """'Thừa Thiên Huế' -> 'thuathienhue'; 'TP. HCM' -> 'tphcm'; 'Giải ĐB' -> 'giaidb'."""
    t = unicodedata.normalize("NFD", text.replace("Đ", "D").replace("đ", "d"))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t.lower())


def province_code(name: str) -> str:
    """Tên đài trên trang -> mã đài viết liền: 'Huế' -> 'thuathienhue', 'Đà Nẵng' -> 'danang'."""
    k = key(name)
    return ALIASES.get(k, k)


def code_key(code: str) -> str:
    return code.replace("-", "")


class _Table(HTMLParser):
    """Đọc bảng đầu tiên có class table-result thành danh sách dòng, mỗi dòng là danh sách ô."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.done = False
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "table":
            if self.depth:
                self.depth += 1
            elif "table-result" in (dict(attrs).get("class") or "").split():
                self.depth = 1
        elif self.depth and tag == "tr":
            self.rows.append([])
        elif self.depth and tag in ("td", "th") and self.rows:
            self._cell = []
        elif self.depth and tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if self.done or not self.depth:
            return
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.done = True

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_mb(markup: str) -> dict[str, list[str]]:
    found = by_class(markup, set(CLASS_TO_PRIZE))
    out: dict[str, list[str]] = {}
    for cls, code in CLASS_TO_PRIZE.items():
        nums = ["".join(ch for ch in v if ch.isdigit()) for v in found.get(cls, [])]
        nums = [n for n in nums if n]
        if nums:
            out[code] = nums
    return out


def parse_multi(markup: str) -> dict[str, dict[str, list[str]]]:
    """{mã đài viết liền: {giải: [số]}} từ bảng nhiều đài. Ô chưa quay ('...') được bỏ qua."""
    t = _Table()
    t.feed(markup)
    t.close()
    if not t.rows:
        raise ParseError("Không tìm thấy bảng table-result")
    header = t.rows[0]
    provinces = [province_code(h) for h in header[1:]]
    out: dict[str, dict[str, list[str]]] = {p: {} for p in provinces}
    for row in t.rows[1:]:
        if len(row) < 2:
            continue
        prize = ROW_TO_PRIZE.get(re.sub(r"^(giai|g)", "", key(row[0])))
        if not prize:
            continue
        for prov, cell in zip(provinces, row[1:]):
            nums = re.findall(r"\d+", cell)
            if nums:
                out[prov][prize] = nums
    return out


# Giữ tên cũ cho mã đã dùng
parse_html = parse_mb


class XosoComVnAdapter(ScrapeAdapter):
    def _url(self, draw: DrawRef) -> str:
        base = self.config.get("base_url", "https://xoso.com.vn")
        if draw.region not in ("mb", "mn", "mt"):
            raise ParseError(f"xoso.com.vn: chưa hỗ trợ miền {draw.region}")
        return f"{base}/xs{draw.region}-{draw.draw_date:%d-%m-%Y}.html"

    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        url = self._url(draw)
        await self.guard(http, url)
        r = await http.get(url, headers=self.headers({"Accept": "text/html"}))
        self.check_blocked(r)
        return FetchResult(url, r.status_code, r.content if r.status_code == 200 else b"", "text/html")

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        markup = result.body.decode("utf-8", errors="replace")
        if draw.region == "mb":
            return Parsed(prizes=parse_mb(markup))
        tables = parse_multi(markup)
        want = code_key((self.config.get("province_map") or {}).get(draw.province, draw.province))
        for prov, prizes in tables.items():
            if prov == want:
                return Parsed(prizes=prizes)
        return Parsed(prizes={})
