"""Bộ cào minhngoc.net cho xổ số miền Nam (và miền Trung nếu bật).

URL: https://www.minhngoc.net/ket-qua-xo-so/mien-nam/<đài>/<dd-mm-yyyy>.html
Trang trả về vài kỳ gần nhất tính đến ngày đó. Cách đọc dựa trên dự án mã nguồn mở
dtbinhtomaydt/xsmn-data: bỏ thẻ HTML, tìm nhãn giải ("Giải ĐB", "Giải nhất"...), lấy chữ số
giữa hai nhãn liền nhau rồi cắt theo số chữ số của từng giải.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from ..config import VN_TZ
from ..domain.prizes import DEFAULT_STRUCTURES
from .base import DrawRef, FetchResult, Parsed, ParseError
from .html_util import strip_tags
from .scrape_base import ScrapeAdapter

REGION_PATH = {"mn": "mien-nam", "mt": "mien-trung"}
LABELS = [
    ("db", r"gi[aả]i\s*đ[ạa]c\s*bi[eệ]t|gi[aả]i\s*đb(?![a-záàảã])"),
    ("g1", r"gi[aả]i\s*nh[aấ]t(?![a-záàảã])"),
    ("g2", r"gi[aả]i\s*nh[iì](?![a-záàảã])"),
    ("g3", r"gi[aả]i\s*ba(?![a-záàảã])"),
    ("g4", r"gi[aả]i\s*t[uư](?![a-záàảã])"),
    ("g5", r"gi[aả]i\s*n[aă]m(?![a-záàảã])"),
    ("g6", r"gi[aả]i\s*s[aá]u(?![a-záàảã])"),
    ("g7", r"gi[aả]i\s*b[aả]y(?![a-záàảã])"),
    ("g8", r"gi[aả]i\s*(?:8|t[aá]m)(?![a-záàảã])"),
]
LABEL_RE = [(k, re.compile(p, re.I)) for k, p in LABELS]
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _dates(text: str) -> list[tuple[date, int, int]]:
    out = []
    for m in DATE_RE.finditer(text):
        try:
            out.append((date(int(m[3]), int(m[2]), int(m[1])), m.start(), m.end()))
        except ValueError:
            pass
    return out


def parse_text(text: str, target: date, region: str = "mn", allow_partial: bool = False) -> dict[str, list[str]]:
    """Tìm kết quả của ngày target trong văn bản trang. Trả về {} nếu không có."""
    spec = {p.code: (p.count, p.digits) for p in DEFAULT_STRUCTURES[region].prizes}
    dates = _dates(text)
    for i, (d, _, end) in enumerate(dates):
        if d != target:
            continue
        seg = text[end: dates[i + 1][1] if i + 1 < len(dates) else len(text)]
        hits = sorted(((m.start(), m.end(), k) for k, rx in LABEL_RE for m in rx.finditer(seg)), key=lambda h: h[0])
        if not hits:
            continue
        found: dict[str, list[str]] = {}
        for j, (_, e, key) in enumerate(hits):
            if key in found:
                continue
            nxt = hits[j + 1][0] if j + 1 < len(hits) else len(seg)
            digits = "".join(re.findall(r"\d+", seg[e:nxt]))
            count, width = spec[key]
            need = count * width
            if len(digits) >= need:
                digits = digits[:need]
            elif not allow_partial:
                continue
            n = len(digits) // width
            if n:
                found[key] = [digits[k * width:(k + 1) * width] for k in range(n)]
        complete = all(len(found.get(k, [])) == c for k, (c, _) in spec.items())
        if complete or (allow_partial and found):
            return found
    return {}


class MinhNgocAdapter(ScrapeAdapter):
    def _url(self, draw: DrawRef) -> str:
        base = self.config.get("base_url", "https://www.minhngoc.net/ket-qua-xo-so")
        path = REGION_PATH.get(draw.region)
        if not path:
            raise ParseError(f"minhngoc: chưa hỗ trợ miền {draw.region}")
        slug = (self.config.get("province_map") or {}).get(draw.province, draw.province)
        return f"{base}/{path}/{slug}/{draw.draw_date:%d-%m-%Y}.html"

    async def fetch(self, http, draw: DrawRef) -> FetchResult:
        url = self._url(draw)
        await self.guard(http, url)
        r = await http.get(url, headers=self.headers({"Accept": "text/html", "Referer": "https://www.minhngoc.net/"}))
        self.check_blocked(r)
        return FetchResult(url, r.status_code, r.content if r.status_code == 200 else b"", "text/html", dict(r.headers))

    def parse(self, result: FetchResult, draw: DrawRef) -> Parsed:
        text = strip_tags(result.body.decode("utf-8", errors="replace"))
        live = draw.draw_date == datetime.now(VN_TZ).date()
        prizes = parse_text(text, draw.draw_date, draw.region, allow_partial=live)
        return Parsed(prizes=prizes)
