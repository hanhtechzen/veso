"""Đọc trang kết quả vietlott.vn cho các trò chơi quay nhiều kỳ hoặc có cơ cấu giải riêng:
Lotto 5/35, Keno, Max 3D, Max 3D Pro, Bingo18.

Mỗi lần gọi trả về một trang (khoảng 5–10 kỳ gần nhất). Địa chỉ, nội dung yêu cầu và cách đọc bảng
lấy theo dự án mã nguồn mở vietvudanh/vietlott-data (đang chạy hằng ngày). Hãy chạy thử bằng
'probe-feed' trước khi bật, vì Vietlott có thể đổi giao diện hoặc khóa yêu cầu.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from ..domain.games import GAMES, MAX3D_PRIZES
from .base import DrawRef, FetchResult, Parsed, ParseError
from .html_util import strip_tags
from .scrape_base import BROWSER_UA, ScrapeAdapter
from .vietlott import ORENDER

BASE = "https://vietlott.vn/ajaxpro/Vietlott.PlugIn.WebParts.{}CompareWebPart,Vietlott.PlugIn.WebParts.ashx"
ROW_RE = re.compile(r"<tr[^>]*>([\s\S]*?)</tr>", re.I)
TD_RE = re.compile(r"<td[^>]*>([\s\S]*?)</td>", re.I)
SPAN_RE = re.compile(r"<span([^>]*)>([\s\S]*?)</span>", re.I)
A_RE = re.compile(r"<a[^>]*>([\s\S]*?)</a>", re.I)
DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


@dataclass
class FeedRow:
    day: date
    seq: int
    prizes: dict[str, list[str]]


def _date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%d/%m/%Y").date()
    except ValueError:
        return None


def _seq(text: str) -> int | None:
    d = re.sub(r"\D", "", strip_tags(text or ""))
    return int(d) if d else None


def _spans(html: str, cls: str | None = None) -> list[str]:
    out = []
    for attrs, inner in SPAN_RE.findall(html):
        if cls and cls not in attrs:
            continue
        t = strip_tags(inner).strip()
        if t and t != "|":
            out.append(t)
    return out


def parse_pick_rows(html: str, main: int, special: bool) -> list[FeedRow]:
    """Bảng kiểu Power/Lotto: cột ngày, cột kỳ, cột các quả bóng (số đặc biệt sau dấu |)."""
    rows = []
    for tr in ROW_RE.findall(html):
        tds = TD_RE.findall(tr)
        if len(tds) < 3:
            continue
        d, seq = _date(strip_tags(tds[0])), _seq(tds[1])
        nums = [re.sub(r"\D", "", n).zfill(2) for n in _spans(tds[2])]
        if not d or seq is None or len(nums) != main + (1 if special else 0):
            continue
        pr = {"main": nums[:main]}
        if special:
            pr["special"] = [nums[main]]
        rows.append(FeedRow(d, seq, pr))
    return rows


def parse_link_rows(html: str, count: int, width: int) -> list[FeedRow]:
    """Bảng kiểu Keno/Bingo18: ô đầu có hai liên kết (ngày, kỳ), ô thứ hai là các quả bóng."""
    rows = []
    for tr in ROW_RE.findall(html):
        tds = TD_RE.findall(tr)
        if len(tds) < 2:
            continue
        links = [strip_tags(a).strip() for a in A_RE.findall(tds[0])]
        d = _date(" ".join(links) or strip_tags(tds[0]))
        seq = _seq(links[1]) if len(links) > 1 else None
        nums = [re.sub(r"\D", "", n) for n in _spans(tds[1])]
        nums = [n.zfill(width) for n in nums if n]
        if not d or seq is None or len(nums) != count:
            continue
        rows.append(FeedRow(d, seq, {"main": nums}))
    return rows


def parse_max3d_rows(html: str) -> list[FeedRow]:
    """Bảng Max 3D: dòng có 'Ngày: dd/mm/yyyy', mã kỳ trong liên kết, 60 chữ số trong các bóng tròn."""
    rows = []
    for tr in ROW_RE.findall(html):
        text = strip_tags(tr)
        if "Ngày" not in text:
            continue
        d = _date(text.split("Ngày", 1)[1])
        tds = TD_RE.findall(tr)
        links = A_RE.findall(tds[0]) if tds else []
        seq = _seq(links[0]) if links else None
        start = tr.find("tong_day_so_ket_qua")
        digits = [re.sub(r"\D", "", s) for s in _spans(tr[start:] if start >= 0 else tr, "bong_tron")]
        digits = [x for x in digits if x]
        if not d or seq is None or len(digits) < 60:
            continue
        flat = "".join(digits[:60])
        pr, i = {}, 0
        for code, _name, n, w in MAX3D_PRIZES:
            pr[code] = [flat[i + k * w:i + (k + 1) * w] for k in range(n)]
            i += n * w
        rows.append(FeedRow(d, seq, pr))
    return rows


CONFIG = {
    "lotto535": {"part": "Game535", "body": lambda p: {"ORenderInfo": ORENDER, "Key": "d0ea794f", "GameDrawId": "",
                                                        "ArrayNumbers": [["" for _ in range(35)] for _ in range(5)],
                                                        "CheckMulti": False, "PageIndex": p}, "first": 0,
                 "parse": lambda h: parse_pick_rows(h, 5, True)},
    "keno": {"part": "GameKeno", "body": lambda p: {"ORenderInfo": ORENDER, "GameId": "6", "GameDrawNo": "", "DrawDate": "",
                                                   "number": "", "OddEven": 2, "UpperLower": 2, "ProcessType": 0,
                                                   "PageIndex": p, "TotalRow": 112453}, "first": 1,
             "parse": lambda h: parse_link_rows(h, 20, 2)},
    "max3d": {"part": "GameMax3D", "body": lambda p: {"ORenderInfo": ORENDER, "GameId": "5", "GameDrawId": "", "CheckMulti": 0,
                                                     "number01": "123", "number02": "321", "PageIndex": p}, "first": 0,
              "parse": parse_max3d_rows},  # trang mới nhất là PageIndex=0
    "max3dpro": {"part": "GameMax3DPro", "body": lambda p: {"ORenderInfo": ORENDER, "GameId": "7", "GameDrawId": "", "CheckMulti": 0,
                                                           "number01": "123", "number02": "321", "PageIndex": p}, "first": 0,
                 "parse": parse_max3d_rows},  # trang mới nhất là PageIndex=0
    "bingo18": {"part": "GameBingo", "body": lambda p: {"ORenderInfo": ORENDER, "GameId": "8", "GameDrawNo": "", "number": "",
                                                       "DrawDate": "", "PageIndex": p, "TotalRow": 45628}, "first": 1,
                "parse": lambda h: parse_link_rows(h, 3, 1)},
}


class VietlottFeedAdapter(ScrapeAdapter):
    """config: {"game": "keno"} (bắt buộc), có thể ghi đè "key", "first_page"."""

    @property
    def user_agent(self) -> str:
        return self.config.get("user_agent") or BROWSER_UA

    @property
    def game(self) -> str:
        g = self.config.get("game")
        if g not in CONFIG:
            raise ParseError(f"vietlott_feed: chưa hỗ trợ trò chơi {g}")
        return g

    async def fetch_page(self, http, page: int) -> tuple[FetchResult, list[FeedRow]]:
        cfg = CONFIG[self.game]
        url = BASE.format(cfg["part"])
        await self.guard(http, url)
        body = cfg["body"](cfg["first"] + page + int(self.config.get("first_page_offset", 0)))
        if self.config.get("key") and "Key" in body:
            body["Key"] = self.config["key"]
        r = await http.post(url, content=json.dumps(body), headers=self.headers({
            "Accept": "*/*", "Content-Type": "text/plain; charset=utf-8", "X-AjaxPro-Method": "ServerSideDrawResult",
            "X-Requested-With": "XMLHttpRequest", "Origin": "https://vietlott.vn", "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong"}))
        self.check_blocked(r)
        if r.status_code != 200:
            return FetchResult(url, r.status_code, b""), []
        try:
            html = r.json()["value"]["HtmlContent"]
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError(f"Vietlott trả dữ liệu không như mong đợi: {e}") from e
        return FetchResult(f"{url}#page={page}", 200, html.encode("utf-8"), "text/html"), cfg["parse"](html)

    # Giữ tương thích với cơ chế lấy theo từng kỳ (dùng cho probe-source và bù kỳ thiếu)
    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        last = None
        for page in range(int(self.config.get("max_pages", 3))):
            res, rows = await self.fetch_page(http, page)
            last = res
            if not rows or any(r.day == draw.draw_date for r in rows) or min(r.day for r in rows) < draw.draw_date:
                break
        return last or FetchResult("", 404, b"")

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        rows = CONFIG[self.game]["parse"](result.body.decode("utf-8", errors="replace"))
        for r in rows:
            if r.day == draw.draw_date:
                return Parsed(prizes=r.prizes, complete=True, meta={"draw_seq": r.seq})
        return Parsed(prizes={})


assert all(g in GAMES for g in CONFIG)

