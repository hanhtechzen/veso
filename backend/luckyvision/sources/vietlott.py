"""Bộ cào trang chính thức vietlott.vn cho Power 6/55.

Gọi cùng endpoint AJAX mà trang kết quả của Vietlott dùng (theo dự án mã nguồn mở
vietvudanh/vietlott-data). Mỗi trang trả về khoảng 6 kỳ; đi lùi theo PageIndex đến khi gặp ngày cần tìm.
Cột kết quả có 7 số: 6 số chính, sau dấu "|" là số đặc biệt.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .base import DrawRef, FetchResult, Parsed, ParseError
from .html_util import strip_tags
from .scrape_base import BROWSER_UA, ScrapeAdapter

URL = "https://vietlott.vn/ajaxpro/Vietlott.PlugIn.WebParts.Game655CompareWebPart,Vietlott.PlugIn.WebParts.ashx"
ORENDER = {"SiteId": "main.frontend.vi", "SiteAlias": "main.vi", "UserSessionId": "", "SiteLang": "vi",
           "IsPageDesign": False, "ExtraParam1": "", "ExtraParam2": "", "ExtraParam3": "", "SiteURL": "",
           "WebPage": None, "SiteName": "Vietlott", "OrgPageAlias": None, "PageAlias": None, "RefKey": None,
           "FullPageAlias": None}
ROW_RE = re.compile(r"<tr[^>]*>([\s\S]*?)</tr>", re.I)
TD_RE = re.compile(r"<td[^>]*>([\s\S]*?)</td>", re.I)
SPAN_RE = re.compile(r"<span[^>]*>([\s\S]*?)</span>", re.I)


def parse_rows(html_content: str, main_count: int = 6, has_special: bool = True) -> list[dict]:
    """[{date, seq, main: [...], special: số hoặc None}] cho mỗi dòng trong bảng kết quả."""
    rows = []
    for tr in ROW_RE.findall(html_content):
        tds = TD_RE.findall(tr)
        if len(tds) < 3:
            continue
        try:
            d = datetime.strptime(strip_tags(tds[0]).strip(), "%d/%m/%Y").date()
        except ValueError:
            continue
        seq_txt = re.sub(r"\D", "", strip_tags(tds[1]))
        nums = [re.sub(r"\D", "", strip_tags(s)) for s in SPAN_RE.findall(tds[2])]
        nums = [n.zfill(2) for n in nums if n]
        if len(nums) != main_count + (1 if has_special else 0):
            continue
        rows.append({"date": d, "seq": int(seq_txt) if seq_txt else None, "main": nums[:main_count],
                     "special": nums[main_count] if has_special else None})
    return rows


class VietlottPower655Adapter(ScrapeAdapter):
    URL = URL
    KEY = "23bbd667"
    ROWS = 5
    MAIN = 6
    SPECIAL = True
    PAGE = "winning-number-655"

    @property
    def user_agent(self) -> str:
        # Endpoint AJAX của Vietlott từ chối User-Agent lạ; mặc định giả lập trình duyệt như dự án gốc.
        return self.config.get("user_agent") or BROWSER_UA

    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        await self.guard(http, self.URL)
        headers = self.headers({
            "Accept": "*/*", "Content-Type": "text/plain; charset=utf-8",
            "X-AjaxPro-Method": "ServerSideDrawResult", "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://vietlott.vn",
            "Referer": "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/" + self.PAGE,
        })
        max_pages = int(self.config.get("max_pages", 10))
        last: FetchResult | None = None
        for page in range(max_pages):
            body = {"ORenderInfo": ORENDER, "Key": self.config.get("key", self.KEY), "GameDrawId": "",
                    "ArrayNumbers": [["" for _ in range(18)] for _ in range(self.ROWS)], "CheckMulti": False,
                    "PageIndex": page}
            r = await http.post(self.URL, content=json.dumps(body), headers=headers)
            self.check_blocked(r)
            if r.status_code != 200:
                return FetchResult(self.URL, r.status_code, b"")
            try:
                content = r.json()["value"]["HtmlContent"]
            except (ValueError, KeyError, TypeError) as e:
                raise ParseError(f"Vietlott trả dữ liệu không như mong đợi: {e}") from e
            rows = parse_rows(content, self.MAIN, self.SPECIAL)
            last = FetchResult(f"{self.URL}#page={page}", 200, content.encode("utf-8"), "text/html")
            if not rows or any(x["date"] == draw.draw_date for x in rows) or min(x["date"] for x in rows) < draw.draw_date:
                return last
        return last or FetchResult(self.URL, 404, b"")

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        for row in parse_rows(result.body.decode("utf-8", errors="replace"), self.MAIN, self.SPECIAL):
            if row["date"] == draw.draw_date:
                prizes = {"main": row["main"]}
                if self.SPECIAL:
                    prizes["special"] = [row["special"]]
                return Parsed(prizes=prizes, complete=True, meta={"draw_seq": row["seq"]})
        return Parsed(prizes={})


class VietlottMega645Adapter(VietlottPower655Adapter):
    """Mega 6/45: cùng cấu trúc bảng với Power 6/55, chỉ có 6 số, không có số đặc biệt
    (theo dự án mã nguồn mở vietvudanh/vietlott-data)."""
    URL = "https://vietlott.vn/ajaxpro/Vietlott.PlugIn.WebParts.Game645CompareWebPart,Vietlott.PlugIn.WebParts.ashx"
    KEY = "8290fce2"
    ROWS = 6
    MAIN = 6
    SPECIAL = False
    PAGE = "winning-number-645"
