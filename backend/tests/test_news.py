"""Tính năng "Tin tức" (test viết trước khi có mã): bộ lọc, bài tự sinh, RSS, dịch vụ CSDL, trang công khai, API quản trị, worker.

Giả định bổ sung ngoài hợp đồng (mã cần tuân theo để test chạy được với CSDL giả):
- region_day_complete chạy MỘT câu SELECT count trên lottery_draws (ví dụ count(*) và count(current_version), hoặc FILTER);
  FakeConn trả hàng "linh hoạt" (FlexRow) vừa truy cập được theo chỉ số (0 = tổng số kỳ, 1 = số kỳ đã có current_version)
  vừa theo tên cột (tên chứa pub/done/ver/ready/ok/complete = số đã công bố, tên khác = tổng).
- on_events lấy dữ liệu kỳ bằng các câu SQL kiểu site/data.py `_draws`: "... FROM lottery_draws d JOIN provinces p ..." và
  "... FROM lottery_results ..." (hàng có các cột như _draws); FakeConn trả toàn bộ dữ liệu kỳ cấu hình sẵn cho mọi câu như vậy.
  Với Vietlott, hàng kỳ có thêm draw_seq; kết quả gồm prize_code "main"/"special".
- Ghi bài: câu INSERT INTO news_articles; test tìm dedupe_key trong tham số (chuỗi), không phụ thuộc thứ tự cột.
- Cột body truyền cho psycopg có thể là Jsonb (thuộc tính .obj) hoặc dict.
- robots_allowed của fetch_feed có thể là hàm đồng bộ hoặc coroutine; test dùng đối tượng vừa falsy vừa awaitable -> False.
- Bộ lọc SQL của trang công khai: nếu câu SQL chứa "hidden" thì FakeDB loại bài ẩn; nếu chứa "order by ... desc" thì FakeDB
  sắp xếp published_at giảm dần; nếu không, mã Python phải tự lọc/sắp xếp. Phân trang: LIMIT/OFFSET lấy từ tham số (hai số
  nguyên cuối) hoặc nhúng trong chuỗi SQL; câu count(*) được trả hàng linh hoạt (mọi tên cột = tổng).
- API quản trị: GET /news, GET /news-feeds trả 200; PATCH trả 200 và ghi "INSERT INTO audit_logs".
"""
from __future__ import annotations

import inspect
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from xs247.api import admin
from xs247.api.errors import install
from xs247.config import VN_TZ, Settings
from xs247.site import routes

BACKEND = Path(__file__).resolve().parents[1]


# ============================ bộ lọc ============================
BANNED_SAMPLES = ["Dự báo kết quả hôm nay", "DỰ ĐOÁN XSMB", "du-doan-xsmb", "Soi cầu miền Bắc", "chốt số đẹp",
                  "Dàn đề 36 số", "lô đề online", "Bạch thủ lô", "dự  báo"]


@pytest.mark.parametrize("text", BANNED_SAMPLES)
def test_filter_blocks_banned_phrases(text):
    from xs247.news.filter import BANNED, is_clean
    assert BANNED.search(text)
    assert is_clean(text) is False


def test_filter_allows_plain_result_text():
    from xs247.news.filter import is_clean
    assert is_clean("Kết quả xổ số miền Bắc ngày 10/11/2026") is True
    assert is_clean("") is True


def test_banned_regex_is_case_insensitive():
    from xs247.news.filter import BANNED
    assert BANNED.flags & re.IGNORECASE


# ============================ bài tự sinh ============================
def _mb_draw(day=date(2026, 11, 10), special="12345"):
    prizes = {"db": [special], "g1": ["67890"], "g2": ["11111", "22222"], "g7": ["05", "17", "29", "93"]}
    nums = [n for v in prizes.values() for n in v]
    return {"id": f"mb-mb-{day.isoformat()}", "province_code": "mb", "province_name": "Miền Bắc", "draw_date": day,
            "prizes": prizes, "loto": [n[-2:] for n in nums]}


def _mn_draw(code, name, special, day=date(2026, 11, 10)):
    prizes = {"g8": ["12"], "db": [special]}
    return {"id": f"mn-{code}-{day.isoformat()}", "province_code": code, "province_name": name, "draw_date": day,
            "prizes": prizes, "loto": ["12", special[-2:]]}


def test_region_day_article_mb_fields():
    from xs247.news.articles import region_day_article
    day = date(2026, 11, 10)
    a = region_day_article("mb", day, [_mb_draw(day)])
    assert a["dedupe_key"] == "region_day:mb:2026-11-10"
    assert a["slug"] == "ket-qua-xsmb-10-11-2026"
    assert "Miền Bắc" in a["title"] and "10/11/2026" in a["title"]
    assert a["region_code"] == "mb" and a["draw_ids"] == ["mb-mb-2026-11-10"]
    assert a["ref_date"] == day and a["topic"] == "region_day" and a["kind"] == "auto"
    assert "12345" in a["summary"] and "Miền Bắc" in a["summary"]
    assert a["body"]["link"] == "/xsmb-10-11-2026"
    assert "12345" in json.dumps(a["body"], ensure_ascii=False, default=str)
    json.dumps(a["body"], ensure_ascii=False)  # phải tuần tự hóa được


def test_region_day_article_mn_lists_every_station_special():
    from xs247.news.articles import region_day_article
    day = date(2026, 11, 10)
    draws = [_mn_draw("tp-hcm", "TP. Hồ Chí Minh", "472899"), _mn_draw("dong-thap", "Đồng Tháp", "929097")]
    a = region_day_article("mn", day, draws)
    assert a["slug"] == "ket-qua-xsmn-10-11-2026" and "Miền Nam" in a["title"]
    assert a["dedupe_key"] == "region_day:mn:2026-11-10"
    for s in ("TP. Hồ Chí Minh", "472899", "Đồng Tháp", "929097"):
        assert s in a["summary"]
    assert a["draw_ids"] == [d["id"] for d in draws]
    assert a["body"]["link"] == "/xsmn-10-11-2026"


def test_region_day_article_mt_name():
    from xs247.news.articles import region_day_article
    a = region_day_article("mt", date(2026, 11, 3), [_mn_draw("da-nang", "Đà Nẵng", "123456", date(2026, 11, 3))])
    assert "Miền Trung" in a["title"] and "03/11/2026" in a["title"]
    assert a["slug"] == "ket-qua-xsmt-03-11-2026"


def _vl_draw(game="power655", seq=1422, special=("18",)):
    return {"id": f"vl-{game}-2026-11-10-{seq:05d}", "draw_date": date(2026, 11, 10), "draw_seq": seq,
            "prizes": {"main": ["05", "11", "23", "34", "40", "52"], "special": list(special)}}


def test_vietlott_power_article():
    from xs247.news.articles import vietlott_article
    d = _vl_draw()
    a = vietlott_article("power655", d)
    assert a["dedupe_key"] == f"vietlott_draw:{d['id']}"
    assert a["slug"] == "vietlott-power-655-ky-01422-10-11-2026"
    assert "Power 6/55" in a["title"] and "#01422" in a["title"] and "10/11/2026" in a["title"]
    for n in d["prizes"]["main"] + ["18"]:
        assert n in a["summary"]
    assert a["kind"] == "auto"


def test_vietlott_mega_article_has_no_money_claims():
    from xs247.news.articles import vietlott_article
    d = _vl_draw("mega645", 1300, special=())
    d["prizes"] = {"main": ["01", "09", "16", "27", "33", "45"]}
    a = vietlott_article("mega645", d)
    assert "Mega 6/45" in a["title"] and "#01300" in a["title"]
    assert a["slug"] == "vietlott-mega-645-ky-01300-10-11-2026"
    for n in d["prizes"]["main"]:
        assert n in a["summary"]
    blob = (a["title"] + a["summary"] + json.dumps(a["body"], ensure_ascii=False, default=str)).lower()
    assert "tỷ" not in blob and "jackpot" not in blob


def test_vietlott_article_rejects_other_games():
    from xs247.news.articles import vietlott_article
    with pytest.raises(ValueError):
        vietlott_article("lotto535", _vl_draw("lotto535"))


def test_weekly_article_fields_and_monday_rule():
    from xs247.news.articles import weekly_article
    monday = date(2026, 11, 9)
    draws = [_mb_draw(monday + timedelta(days=i), special=f"1000{i}") for i in range(7)]
    a = weekly_article("mb", monday, draws)
    assert a["topic"] == "weekly_stats" and a["kind"] == "auto"
    assert a["dedupe_key"] == "weekly:mb:2026-11-09"
    assert a["slug"] == "thong-ke-tuan-xsmb-09-11-2026"
    assert a["region_code"] == "mb"
    json.dumps(a["body"], ensure_ascii=False, default=str)
    with pytest.raises(ValueError):
        weekly_article("mb", date(2026, 11, 10), draws)  # thứ Ba


def test_all_generated_articles_are_clean():
    from xs247.news.articles import region_day_article, vietlott_article, weekly_article
    from xs247.news.filter import is_clean
    monday = date(2026, 11, 9)
    arts = [region_day_article("mb", date(2026, 11, 10), [_mb_draw()]),
            region_day_article("mn", date(2026, 11, 10), [_mn_draw("tp-hcm", "TP. Hồ Chí Minh", "472899")]),
            vietlott_article("power655", _vl_draw()),
            weekly_article("mb", monday, [_mb_draw(monday + timedelta(days=i)) for i in range(7)])]
    for a in arts:
        assert is_clean(a["title"]) and is_clean(a["summary"]) and is_clean(str(a["body"])), a["slug"]


# ============================ RSS ============================
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Báo A</title>
<item><title>Kết quả xổ số miền Bắc hôm nay</title><link>https://a.vn/kq-mb</link>
<description><![CDATA[<p>Giải <b>đặc biệt</b> về <a href="x">12345</a></p>]]></description>
<pubDate>Tue, 10 Nov 2026 08:30:00 +0700</pubDate></item>
<item><title>Tin không có liên kết</title><description>x</description></item>
<item><link>https://a.vn/no-title</link><description>x</description></item>
<item><title>Dự báo xổ số ngày mai</title><link>https://a.vn/db</link><description>soi cầu</description></item>
<item><title>Tin xổ số điện toán</title><link>https://a.vn/dt</link><description>Vietlott</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Báo B</title>
<entry><title>Kết quả Power 6/55</title><link href="https://b.vn/power" rel="alternate"/>
<summary>&lt;p&gt;Kỳ quay mới&lt;/p&gt;</summary><updated>2026-11-10T08:30:00+07:00</updated></entry>
<entry><title>Thiếu liên kết</title><summary>x</summary></entry>
</feed>"""


def test_parse_feed_rss_basic_fields():
    from xs247.news.rss import parse_feed
    items = parse_feed(RSS, "Báo A")
    first = items[0]
    assert first["title"] == "Kết quả xổ số miền Bắc hôm nay"
    assert first["url"] == "https://a.vn/kq-mb" and first["source_name"] == "Báo A"
    assert "<" not in first["summary"] and "12345" in first["summary"] and "đặc biệt" in first["summary"]
    assert first["published_at"] == datetime(2026, 11, 10, 8, 30, tzinfo=VN_TZ)
    assert first["published_at"].tzinfo is not None


def test_parse_feed_skips_items_without_title_or_link():
    from xs247.news.rss import parse_feed
    titles = [i["title"] for i in parse_feed(RSS, "Báo A")]
    assert "Tin không có liên kết" not in titles
    assert len(titles) == 3


def test_parse_feed_atom_entries():
    from xs247.news.rss import parse_feed
    items = parse_feed(ATOM, "Báo B")
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "Kết quả Power 6/55" and it["url"] == "https://b.vn/power"
    assert it["summary"] == "Kỳ quay mới"
    assert it["published_at"].utcoffset() == timedelta(hours=7)
    assert it["published_at"] == datetime(2026, 11, 10, 8, 30, tzinfo=VN_TZ)


def test_parse_feed_missing_date_is_none():
    from xs247.news.rss import parse_feed
    xml = "<rss><channel><item><title>T</title><link>https://a.vn/1</link></item></channel></rss>"
    assert parse_feed(xml, "A")[0]["published_at"] is None


def test_parse_feed_truncates_long_summary():
    from xs247.news.rss import parse_feed
    xml = ("<rss><channel><item><title>T</title><link>https://a.vn/1</link><description>" + "a" * 900 +
           "</description></item></channel></rss>")
    s = parse_feed(xml, "A")[0]["summary"]
    assert len(s) <= 300 and s.endswith("…")


def test_parse_feed_short_summary_not_truncated():
    from xs247.news.rss import parse_feed
    xml = "<rss><channel><item><title>T</title><link>https://a.vn/1</link><description>ngắn</description></item></channel></rss>"
    assert parse_feed(xml, "A")[0]["summary"] == "ngắn"


@pytest.mark.parametrize("decl", ["<!DOCTYPE rss>", '<!DOCTYPE foo [<!ENTITY x "y">]>', '<!ENTITY a "b">'])
def test_parse_feed_rejects_doctype_and_entity(decl):
    from xs247.news.rss import parse_feed
    with pytest.raises(ValueError):
        parse_feed(decl + "<rss><channel></channel></rss>", "A")


def _items():
    from xs247.news.rss import parse_feed
    return parse_feed(RSS, "Báo A")


def test_select_items_none_pattern_keeps_clean_only():
    from xs247.news.rss import select_items
    titles = [i["title"] for i in select_items(_items(), None)]
    assert "Dự báo xổ số ngày mai" not in titles
    assert "Kết quả xổ số miền Bắc hôm nay" in titles and "Tin xổ số điện toán" in titles


def test_select_items_include_pattern_case_insensitive_on_title_or_summary():
    from xs247.news.rss import select_items
    titles = [i["title"] for i in select_items(_items(), "VIETLOTT|miền bắc")]
    assert sorted(titles) == ["Kết quả xổ số miền Bắc hôm nay", "Tin xổ số điện toán"]


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class _Http:
    def __init__(self, resp):
        self.resp, self.urls = resp, []

    async def get(self, url, *a, **k):
        self.urls.append(url)
        return self.resp


FEED = {"code": "a", "name": "Báo A", "url": "https://a.vn/rss", "include_pattern": "xổ số"}


async def test_fetch_feed_returns_selected_items():
    from xs247.news.rss import fetch_feed
    http = _Http(_Resp(RSS))
    items = await fetch_feed(http, FEED)
    assert http.urls == ["https://a.vn/rss"]
    assert [i["title"] for i in items] == ["Kết quả xổ số miền Bắc hôm nay", "Tin xổ số điện toán"]
    assert all(i["source_name"] == "Báo A" for i in items)


class _Denied:
    """Falsy và awaitable -> False: dùng được cho cả `if not f(url)` lẫn `if not await f(url)`."""
    def __bool__(self):
        return False

    def __await__(self):
        async def _f():
            return False
        return _f().__await__()


async def test_fetch_feed_robots_denied_returns_empty_without_fetching():
    from xs247.news.rss import fetch_feed
    http = _Http(_Resp(RSS))
    assert await fetch_feed(http, FEED, robots_allowed=lambda url, *a: _Denied()) == []
    assert http.urls == []


async def test_fetch_feed_non_200_raises_runtime_error():
    from xs247.news.rss import fetch_feed
    with pytest.raises(RuntimeError):
        await fetch_feed(_Http(_Resp("", 503)), FEED)


async def test_fetch_feed_oversize_body_raises_value_error():
    from xs247.news.rss import fetch_feed
    with pytest.raises(ValueError):
        await fetch_feed(_Http(_Resp("x" * 2_000_001)), FEED)


# ============================ migration ============================
def test_migration_018_defines_news_tables():
    p = BACKEND / "xs247" / "migrations" / "018_news.sql"
    assert p.exists()
    sql = p.read_text(encoding="utf-8").lower()
    for name in ("news_feeds", "news_articles", "include_pattern", "respect_robots", "min_interval_s", "last_fetched_at",
                 "last_ok", "last_error", "dedupe_key", "draw_ids", "ref_date", "source_name", "source_url", "feed_code",
                 "published_at", "updated_at", "hidden", "jsonb", "'auto'", "'external'", "unique"):
        assert name in sql, name


# ============================ dịch vụ CSDL ============================
class FlexRow(dict):
    def __init__(self, total, published):
        super().__init__(total=total, published=published)
        self._vals = [total, published]

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        if any(t in str(k).lower() for t in ("pub", "done", "ver", "ready", "ok", "complete")):
            return self._vals[1]
        return self._vals[0]

    def get(self, k, default=None):
        return self[k]


class Cur:
    def __init__(self, rows=None, row=None):
        self.rows = rows if rows is not None else ([] if row is None else [row])

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class _CM:
    def __init__(self, v):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *a):
        return False


class FakeConn:
    def __init__(self, draws=None, results=None, total=0, published=0):
        self.draws, self.results = draws or [], results or []
        self.total, self.published = total, published
        self.sql: list[str] = []
        self.inserts: list[tuple[str, tuple]] = []

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        low = s.lower()
        self.sql.append(s)
        if low.startswith("insert into news_articles"):
            self.inserts.append((s, tuple(params or ())))
            return Cur()
        if "from lottery_results" in low:
            return Cur(rows=list(self.results))
        if "count(" in low and "lottery_draws" in low and "join provinces" not in low:
            return Cur(row=FlexRow(self.total, self.published))
        if "from lottery_draws" in low:
            return Cur(rows=list(self.draws))
        return Cur()

    def transaction(self):
        return _CM(None)

    def cursor(self):
        return _CM(self)


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def connection(self):
        return _CM(self.conn)


def _keys(conn):
    return [p for _, params in conn.inserts for p in params if isinstance(p, str) and ":" in p
            and p.split(":")[0] in ("region_day", "vietlott_draw", "weekly")]


async def test_region_day_complete_true_when_all_have_version():
    from xs247.news.service import region_day_complete
    assert await region_day_complete(FakeConn(total=3, published=3), "mn", date(2026, 11, 10)) is True


async def test_region_day_complete_false_when_some_unpublished():
    from xs247.news.service import region_day_complete
    assert await region_day_complete(FakeConn(total=3, published=2), "mn", date(2026, 11, 10)) is False


async def test_region_day_complete_false_when_no_draws():
    from xs247.news.service import region_day_complete
    assert await region_day_complete(FakeConn(total=0, published=0), "mn", date(2026, 11, 10)) is False


async def test_upsert_article_auto_uses_do_update():
    from xs247.news.articles import region_day_article
    from xs247.news.service import upsert_article
    art = region_day_article("mb", date(2026, 11, 10), [_mb_draw()])
    conn = FakeConn()
    await upsert_article(conn, art)
    sql, params = conn.inserts[0]
    assert "on conflict (dedupe_key) do update" in sql.lower()
    assert art["dedupe_key"] in params


async def test_upsert_article_external_does_nothing_on_conflict():
    from xs247.news.service import upsert_article
    art = {"kind": "external", "topic": "external", "dedupe_key": "ext:a:https://a.vn/1", "slug": None, "title": "T",
           "summary": "S", "body": None, "region_code": None, "draw_ids": None, "ref_date": None, "source_name": "Báo A",
           "source_url": "https://a.vn/1", "feed_code": "a", "published_at": datetime(2026, 11, 10, 8, 0, tzinfo=VN_TZ)}
    conn = FakeConn()
    await upsert_article(conn, art)
    sql, params = conn.inserts[0]
    assert "on conflict (dedupe_key) do nothing" in sql.lower()
    assert "ext:a:https://a.vn/1" in params


def _mb_conn(total=1, published=1):
    d = _mb_draw()
    rows = [{"id": d["id"], "region_code": "mb", "province_code": "mb", "draw_date": d["draw_date"], "draw_seq": None,
             "current_version": 1, "pname": "Miền Bắc", "game": "xs"}]
    res = [{"draw_id": d["id"], "prize_code": c, "position": i, "number": n}
           for c, v in d["prizes"].items() for i, n in enumerate(v)]
    return FakeConn(draws=rows, results=res, total=total, published=published)


def _event(typ, region, draw_id="mb-mb-2026-11-10", province="mb", version=1):
    return {"type": typ, "payload": {"draw_id": draw_id, "region": region, "province": province, "version": version}}


@pytest.mark.parametrize("typ", ["draw.published", "draw.corrected"])
async def test_on_events_writes_region_roundup_when_complete(typ):
    from xs247.news.service import on_events
    conn = _mb_conn()
    await on_events(FakePool(conn), [_event(typ, "mb")])
    assert "region_day:mb:2026-11-10" in _keys(conn)
    assert "do update" in conn.inserts[0][0].lower()


async def test_on_events_skips_region_roundup_when_day_incomplete():
    from xs247.news.service import on_events
    conn = _mb_conn(total=2, published=1)
    await on_events(FakePool(conn), [_event("draw.published", "mb")])
    assert conn.inserts == []


async def test_on_events_ignores_other_event_types():
    from xs247.news.service import on_events
    conn = _mb_conn()
    await on_events(FakePool(conn), [_event("draw.needs_review", "mb"), _event("collector.failed", "mb")])
    assert conn.inserts == []


@pytest.mark.parametrize("region", ["keno", "bingo", "lotto", "max3d"])
async def test_on_events_ignores_non_roundup_regions(region):
    from xs247.news.service import on_events
    conn = _mb_conn()
    await on_events(FakePool(conn), [_event("draw.published", region, f"{region}-x-2026-11-10", region)])
    assert conn.inserts == []


@pytest.mark.parametrize("region,game", [("vl", "power655"), ("mega", "mega645")])
async def test_on_events_writes_vietlott_article(region, game):
    from xs247.news.service import on_events
    did = f"vl-{game}-2026-11-10-01422"
    rows = [{"id": did, "region_code": region, "province_code": game, "draw_date": date(2026, 11, 10), "draw_seq": 1422,
             "current_version": 1, "pname": game, "game": game}]
    res = [{"draw_id": did, "prize_code": "main", "position": i, "number": n}
           for i, n in enumerate(["05", "11", "23", "34", "40", "52"])]
    conn = FakeConn(draws=rows, results=res, total=1, published=1)
    await on_events(FakePool(conn), [_event("draw.published", region, did, game)])
    assert f"vietlott_draw:{did}" in _keys(conn)


async def test_on_events_needs_no_telegram_settings():
    from xs247.news.service import on_events
    assert list(inspect.signature(on_events).parameters) == ["pool", "rows"]


# ============================ trang công khai ============================
def _art(i, **kw):
    base = {"id": i, "kind": "auto", "topic": "region_day", "dedupe_key": f"region_day:mb:{i}", "slug": f"bai-{i}",
            "title": f"Bài số {i}", "summary": f"Tóm tắt {i}", "body": None, "region_code": "mb", "draw_ids": [],
            "ref_date": date(2026, 11, 10), "source_name": None, "source_url": None, "feed_code": None,
            "published_at": datetime(2026, 11, 1, 6, 0, tzinfo=VN_TZ) + timedelta(hours=i),
            "updated_at": datetime(2026, 11, 1, 6, 0, tzinfo=VN_TZ) + timedelta(hours=i), "hidden": False}
    base.update(kw)
    return base


class NewsDB:
    def __init__(self, articles):
        self.articles = articles
        self.sql: list[str] = []

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        low = s.lower()
        self.sql.append(s)
        params = tuple(params or ())
        if "from news_articles" not in low:
            return Cur()
        rows = list(self.articles)
        if "hidden" in low:
            rows = [r for r in rows if not r["hidden"]]
        if any(isinstance(p, str) for p in params):
            slugs = [p for p in params if isinstance(p, str)]
            return Cur(rows=[r for r in rows if r["slug"] is not None and r["slug"] in slugs][:1])
        if "count(" in low:
            row = FlexRow(len(rows), len(rows))
            return Cur(row=row)
        if "order by" in low and "desc" in low:
            rows.sort(key=lambda r: r["published_at"], reverse=True)
        ints = [p for p in params if isinstance(p, int) and not isinstance(p, bool)]
        m_l, m_o = re.search(r"limit\s+(\d+)", low), re.search(r"offset\s+(\d+)", low)
        limit = int(m_l.group(1)) if m_l else (ints[-2] if len(ints) >= 2 else (ints[-1] if ints else None))
        offset = int(m_o.group(1)) if m_o else (ints[-1] if len(ints) >= 2 else 0)
        rows = rows[offset:]
        return Cur(rows=rows[:limit] if limit is not None else rows)


def _site_app(articles):
    app = FastAPI()
    app.include_router(routes.router)
    app.state.pool = FakePool(NewsDB(articles))
    app.state.settings = Settings(_env_file=None)
    return app


def _get(app, url):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(url)
    return go()


def test_subnav_has_news_link():
    assert ("/tin-tuc", "Tin tức", "tintuc") in routes.SUBNAV["kq"]


async def test_news_list_shows_visible_newest_first_and_hides_hidden():
    arts = [_art(1, title="Bài cũ nhất"), _art(2, title="Bài giữa"), _art(3, title="Bài mới nhất"),
            _art(4, title="Bài bị ẩn", hidden=True, published_at=datetime(2026, 11, 20, tzinfo=VN_TZ))]
    r = await _get(_site_app(arts), "/tin-tuc")
    assert r.status_code == 200, r.text[:300]
    h = r.text
    assert "Bài bị ẩn" not in h
    assert h.index("Bài mới nhất") < h.index("Bài giữa") < h.index("Bài cũ nhất")
    assert 'href="/tin-tuc/bai-3"' in h
    assert "noindex" not in h


async def test_news_list_external_item_links_out_with_nofollow_blank_and_source():
    ext = _art(9, kind="external", topic="external", slug=None, title="Tin ngoài", source_name="Báo Ví Dụ",
               source_url="https://bao.example/tin-1", dedupe_key="ext:1", feed_code="a")
    r = await _get(_site_app([ext]), "/tin-tuc")
    assert r.status_code == 200
    tag = re.search(r'<a\b[^>]*href="https://bao\.example/tin-1"[^>]*>', r.text)
    assert tag, r.text[:500]
    assert "nofollow" in tag.group(0) and 'target="_blank"' in tag.group(0)
    assert "Báo Ví Dụ" in r.text
    assert "/tin-tuc/None" not in r.text


async def test_news_list_page_two_is_noindex():
    arts = [_art(i) for i in range(1, 201)]
    r = await _get(_site_app(arts), "/tin-tuc?trang=2")
    assert r.status_code == 200
    assert re.search(r'<meta\s+name="robots"\s+content="noindex', r.text)


async def test_news_detail_renders_title_and_newsarticle_jsonld():
    from xs247.news.articles import region_day_article
    a = region_day_article("mb", date(2026, 11, 10), [_mb_draw()])
    row = _art(5, slug=a["slug"], title=a["title"], summary=a["summary"], body=a["body"], dedupe_key=a["dedupe_key"])
    r = await _get(_site_app([row]), "/tin-tuc/" + a["slug"])
    assert r.status_code == 200, r.text[:300]
    assert a["title"] in r.text and "NewsArticle" in r.text


async def test_news_detail_unknown_slug_is_404_html():
    r = await _get(_site_app([_art(1)]), "/tin-tuc/khong-co-bai-nay")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]


async def test_news_detail_external_item_is_never_resolvable():
    ext = _art(9, kind="external", topic="external", slug=None, title="Tin ngoài", source_name="B",
               source_url="https://bao.example/x", dedupe_key="ext:9")
    app = _site_app([ext])
    for slug in ("None", "tin-ngoai", "null"):
        assert (await _get(app, "/tin-tuc/" + slug)).status_code == 404


async def test_sitemap_includes_news_index():
    r = await _get(_site_app([]), "/sitemap.xml")
    assert r.status_code == 200
    assert re.search(r"/tin-tuc</loc>", r.text)


# ============================ API quản trị ============================
TOK = {"viewer": "v" * 32, "editor": "e" * 32, "admin": "a" * 32}


class AdminDB:
    def __init__(self, legal=True):
        self.sql: list[str] = []
        self.row = {"legal_approved": legal,"id": 7, "kind": "auto", "topic": "region_day", "dedupe_key": "k", "slug": "s", "title": "T",
                    "summary": "S", "hidden": False, "published_at": datetime(2026, 11, 10, tzinfo=VN_TZ),
                    "updated_at": datetime(2026, 11, 10, tzinfo=VN_TZ), "code": "a", "name": "Báo A",
                    "url": "https://a.vn/rss", "enabled": False, "include_pattern": None, "respect_robots": True,
                    "min_interval_s": 900, "last_fetched_at": None, "last_ok": None, "last_error": None}

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.sql.append(s)
        if "news_articles" in s or "news_feeds" in s:
            return Cur(rows=[dict(self.row)])
        return Cur()


def _admin_app(monkeypatch, legal=True):
    db = AdminDB(legal)
    settings = Settings(_env_file=None, admin_tokens=",".join(f"{t}:{r}:{r}-user" for r, t in TOK.items()))
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    app = FastAPI()
    install(app)
    app.include_router(admin.router)
    app.state.pool = FakePool(db)
    app.state.settings = settings
    return app, db


def _acl(app, role):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                             headers={"Authorization": f"Bearer {TOK[role]}"})


async def test_admin_list_news_viewer_ok_and_has_items(monkeypatch):
    app, _ = _admin_app(monkeypatch)
    async with _acl(app, "viewer") as c:
        r = await c.get("/v1/admin/news")
    assert r.status_code == 200 and isinstance(r.json()["items"], list)


async def test_admin_list_news_requires_token(monkeypatch):
    app, _ = _admin_app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/v1/admin/news", headers={"Authorization": "Bearer " + "x" * 32})
    assert r.status_code == 401


async def test_admin_patch_news_viewer_forbidden_and_no_write(monkeypatch):
    app, db = _admin_app(monkeypatch)
    async with _acl(app, "viewer") as c:
        r = await c.patch("/v1/admin/news/7", json={"hidden": True})
    assert r.status_code == 403
    assert not any(s.lower().startswith("update news_articles") for s in db.sql)


async def test_admin_patch_news_editor_updates_and_audits(monkeypatch):
    app, db = _admin_app(monkeypatch)
    async with _acl(app, "editor") as c:
        r = await c.patch("/v1/admin/news/7", json={"hidden": True})
    assert r.status_code == 200, r.text
    assert any(s.lower().startswith("update news_articles") for s in db.sql)
    assert any(s.startswith("INSERT INTO audit_logs") for s in db.sql)


async def test_admin_patch_news_rejects_missing_hidden(monkeypatch):
    app, db = _admin_app(monkeypatch)
    async with _acl(app, "editor") as c:
        r = await c.patch("/v1/admin/news/7", json={})
    assert r.status_code in (400, 422)
    assert not any(s.lower().startswith("update news_articles") for s in db.sql)


async def test_admin_list_feeds_viewer_ok(monkeypatch):
    app, _ = _admin_app(monkeypatch)
    async with _acl(app, "viewer") as c:
        r = await c.get("/v1/admin/news-feeds")
    assert r.status_code == 200


async def test_admin_patch_feed_editor_forbidden(monkeypatch):
    app, db = _admin_app(monkeypatch)
    async with _acl(app, "editor") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"enabled": True})
    assert r.status_code == 403
    assert not any(s.lower().startswith("update news_feeds") for s in db.sql)


async def test_admin_patch_feed_admin_updates_and_audits(monkeypatch):
    app, db = _admin_app(monkeypatch)
    async with _acl(app, "admin") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert any(s.lower().startswith("update news_feeds") for s in db.sql)
    assert any(s.startswith("INSERT INTO audit_logs") for s in db.sql)


async def test_admin_enable_feed_without_legal_approval_is_409(monkeypatch):
    app, db = _admin_app(monkeypatch, legal=False)
    async with _acl(app, "admin") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"enabled": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "legal_not_approved"
    assert not any(s.lower().startswith("update news_feeds") for s in db.sql)


async def test_admin_disable_feed_without_legal_approval_is_allowed(monkeypatch):
    app, _ = _admin_app(monkeypatch, legal=False)
    async with _acl(app, "admin") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"enabled": False})
    assert r.status_code == 200


async def test_admin_set_legal_approved_requires_admin(monkeypatch):
    app, db = _admin_app(monkeypatch, legal=False)
    async with _acl(app, "editor") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"legal_approved": True})
    assert r.status_code == 403
    assert not any(s.lower().startswith("update news_feeds") for s in db.sql)


async def test_admin_set_legal_approved_by_admin_updates_and_audits(monkeypatch):
    app, db = _admin_app(monkeypatch, legal=False)
    async with _acl(app, "admin") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"legal_approved": True})
    assert r.status_code == 200, r.text
    assert any(s.lower().startswith("update news_feeds") and "legal_approved" in s for s in db.sql)
    assert any(s.startswith("INSERT INTO audit_logs") for s in db.sql)


async def test_admin_enable_feed_after_approval_is_200(monkeypatch):
    app, _ = _admin_app(monkeypatch, legal=True)
    async with _acl(app, "admin") as c:
        r = await c.patch("/v1/admin/news-feeds/a", json={"enabled": True})
    assert r.status_code == 200


def test_migration_018_has_legal_approved_default_false():
    sql = (BACKEND / "xs247" / "migrations" / "018_news.sql").read_text(encoding="utf-8").lower()
    assert re.search(r"legal_approved\s+bool\w*\s+(not null\s+)?default\s+false", sql)


# ============================ pubDate, img, "Theo <nguồn>" ============================
def _one(pub=None, desc="x"):
    p = f"<pubDate>{pub}</pubDate>" if pub is not None else ""
    return (f"<rss><channel><item><title>T</title><link>https://a.vn/1</link><description><![CDATA[{desc}]]></description>"
            f"{p}</item></channel></rss>")


@pytest.mark.parametrize("pub,expected", [
    ("Mon, 23 Nov 2026 09:26:17 +0700", datetime(2026, 11, 23, 9, 26, 17, tzinfo=VN_TZ)),
    ("Mon, 23 Nov 26 10:04:00 +0700", datetime(2026, 11, 23, 10, 4, 0, tzinfo=VN_TZ)),
    ("11/23/2026 8:51:00 AM", datetime(2026, 11, 23, 8, 51, 0, tzinfo=VN_TZ)),
    ("11/23/2026 8:51:00 PM", datetime(2026, 11, 23, 20, 51, 0, tzinfo=VN_TZ)),
])
def test_parse_feed_pubdate_formats(pub, expected):
    from xs247.news.rss import parse_feed
    got = parse_feed(_one(pub), "A")[0]["published_at"]
    assert got is not None and got.tzinfo is not None and got == expected


def test_parse_feed_unparseable_pubdate_keeps_item_with_none():
    from xs247.news.rss import parse_feed
    items = parse_feed(_one("không phải ngày"), "A")
    assert len(items) == 1 and items[0]["published_at"] is None


def test_parse_feed_strips_img_tags():
    from xs247.news.rss import parse_feed
    s = parse_feed(_one(None, '<a href="x"><img src="y"></a>Nội dung'), "A")[0]["summary"]
    assert s == "Nội dung"


async def test_news_list_external_item_shows_theo_source_name():
    ext = _art(9, kind="external", topic="external", slug=None, title="Tin ngoài", source_name="Báo Thanh Niên",
               source_url="https://thanhnien.vn/x", dedupe_key="ext:9", feed_code="thanhnien")
    r = await _get(_site_app([ext]), "/tin-tuc")
    assert r.status_code == 200 and "Theo Báo Thanh Niên" in r.text


# ============================ worker ============================
def test_worker_run_registers_news_jobs_and_events_hook():
    from xs247.worker import Worker
    src = inspect.getsource(Worker.run)
    for job in ("news-sweep", "news-weekly", "news-feeds"):
        assert job in src, job
    assert "news" in src and "on_events" in src
    assert "news" in src[src.index("async def after"):].split("relay =")[0]
