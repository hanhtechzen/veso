"""Dò vé giấy công khai: POST /v1/check-ticket (module xs247.api.check, biến `router`, đối tượng `LIMIT`).

Giả định (lỏng, theo từ khóa SQL; không Postgres thật):
  * "lottery_results"  -> các hàng {draw_id, prize_code, number, position} của phiên bản hiện hành của kỳ quay
                          (tham số có thể là mã kỳ hoặc list mã kỳ).
  * "from provinces"   -> hàng {code, name, region_code, game, active} theo mã (tham số đầu).
  * "lottery_draws"    -> hàng kỳ quay {id, game, region_code, province_code, draw_date, scheduled_at,
                          current_version, status} theo mã kỳ (tham số đầu); không có -> không hàng.
  * Không được ghi gì (chỉ SELECT): không INSERT/UPDATE/DELETE.
Giới hạn tần suất: 30 lần/phút theo IP (header cf-connecting-ip hoặc client.host), bằng `xs247.api.check.LIMIT`
(một `xs247.ai.RateLimiter`). Test đặt lại bằng cách monkeypatch thuộc tính module `LIMIT` thành RateLimiter() mới.
Ngày cố định, không phụ thuộc giờ hệ thống.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from xs247.api.errors import install
from xs247.collector.planner import make_draw_id
from xs247.config import VN_TZ

DAY = date(2026, 11, 12)
MB = {"db": ["12345"], "g1": ["67890"], "g4": ["1234", "5678"], "g7": ["45", "99", "05"]}
MN = {"db": ["123456"], "g1": ["78901"], "g2": ["23456"], "g3": ["11111", "22222"], "g4": ["33333"],
      "g5": ["4444"], "g6": ["5555", "6666", "7777"], "g7": ["888"], "g8": ["12"]}
P655 = {"main": ["03", "09", "14", "27", "40", "55"], "special": ["07"]}
M645 = {"main": ["03", "09", "14", "27", "40", "45"]}

PROVINCES = {
    "mb": {"code": "mb", "name": "Miền Bắc", "region_code": "mb", "game": "xs", "active": True},
    "tphcm": {"code": "tphcm", "name": "TP.HCM", "region_code": "mn", "game": "xs", "active": True},
}


def _draw(did, game, region, province, version):
    return {"id": did, "game": game, "region_code": region, "province_code": province, "draw_date": DAY,
            "scheduled_at": datetime(2026, 11, 12, 18, 15, tzinfo=VN_TZ), "current_version": version,
            "status": "published" if version else "scheduled"}


MB_ID = make_draw_id("mb", "mb", DAY)
MN_ID = make_draw_id("mn", "tphcm", DAY)
P_ID = make_draw_id("vl", "power655", DAY)
M_ID = make_draw_id("mega", "mega645", DAY)  # Mega có mã miền riêng "mega" (migration 008)


class Cur:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.rowcount = len(self.rows)

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class FakeDB:
    def __init__(self, draws=None, prizes=None):
        self.draws = draws or {}          # id -> hàng kỳ quay
        self.prizes = prizes or {}        # id -> {prize_code: [number, ...]}
        self.sql: list[str] = []

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        p = tuple(params or ())
        self.sql.append(s)
        low = s.lower()
        if "lottery_results" in low:
            ids = set()
            for x in p:
                ids.update(x if isinstance(x, (list, tuple)) else [x])
            rows = []
            for did in ids:
                d = self.draws.get(did)
                if not d or d.get("current_version") is None:
                    continue
                pos = 0
                for code, nums in self.prizes.get(did, {}).items():
                    for n in nums:
                        rows.append({"draw_id": did, "prize_code": code, "number": n, "position": pos,
                                     "version": d["current_version"]})
                        pos += 1
            return Cur(rows)
        if "from provinces" in low:
            row = PROVINCES.get(p[0]) if p else None
            return Cur([row] if row else [])
        if "lottery_draws" in low:
            row = next((self.draws[x] for x in p if isinstance(x, str) and x in self.draws), None)
            return Cur([row] if row else [])
        return Cur()

    def writes(self):
        return [s for s in self.sql if s.lower().startswith(("insert", "update", "delete"))]


class FakePool:
    def __init__(self, db):
        self.db = db

    def connection(self):
        db = self.db

        class CM:
            async def __aenter__(self_):
                return db

            async def __aexit__(self_, *a):
                return False

        return CM()


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    from xs247.ai import RateLimiter
    from xs247.api import check as check_api
    monkeypatch.setattr(check_api, "LIMIT", RateLimiter())


def make_app(db):
    from xs247.api import check as check_api
    a = FastAPI()
    install(a)
    a.include_router(check_api.router)
    a.state.pool = FakePool(db)
    a.state.collector = SimpleNamespace(http=None)
    return a


def cl(app, headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers or {})


def full_db():
    draws = {
        MB_ID: _draw(MB_ID, "xs", "mb", "mb", 1),
        MN_ID: _draw(MN_ID, "xs", "mn", "tphcm", 1),
        P_ID: _draw(P_ID, "power655", "vl", "power655", 1),
        M_ID: _draw(M_ID, "mega645", "mega", "mega645", 1),
    }
    return FakeDB(draws, {MB_ID: MB, MN_ID: MN, P_ID: P655, M_ID: M645})


def xs_body(lines, province="mb"):
    return {"game": "xs", "province": province, "draw_date": "2026-11-12", "lines": lines}


def codes(line):
    return {x["code"] for x in line["result"]}


async def post(db, body, headers=None):
    async with cl(make_app(db), headers) as c:
        return await c.post("/v1/check-ticket", json=body)


# ------------------------------------------------------------------ trường hợp chính
async def test_mb_ticket_wins_db_and_g7_public_no_csrf_no_login_no_store():
    db = full_db()
    r = await post(db, xs_body(["12345"]))   # không cookie, không X-LV-CSRF
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["published"] is True
    assert j["draw"]["id"] == MB_ID and j["draw"]["province"] == "mb" and j["draw"]["region"] == "mb"
    assert j["draw"]["game"] == "xs" and j["draw"]["draw_date"] == "2026-11-12"
    assert j["lines"][0]["numbers"] == ["12345"]
    assert codes(j["lines"][0]) == {"db", "g7"}
    assert all(isinstance(x["name"], str) and x["name"] for x in j["lines"][0]["result"])
    assert "no-store" in r.headers["cache-control"]
    assert not db.writes()


async def test_mb_losing_ticket_has_empty_result_list():
    r = await post(full_db(), xs_body(["00000"]))
    assert r.status_code == 200
    assert r.json()["lines"][0]["result"] == []


async def test_mn_ticket_wins_phu_db_and_g2():
    r = await post(full_db(), xs_body(["923456"], province="tphcm"))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["draw"]["id"] == MN_ID and j["draw"]["region"] == "mn"
    assert codes(j["lines"][0]) == {"g2", "phu_db"}


async def test_power655_five_plus_special_is_jackpot2():
    body = {"game": "power655", "draw_date": "2026-11-12", "lines": [[3, 9, 14, 27, 40, 7]]}
    r = await post(full_db(), body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["draw"]["id"] == P_ID and j["draw"]["game"] == "power655"
    assert j["lines"][0]["numbers"] == ["03", "07", "09", "14", "27", "40"]
    assert [x["code"] for x in j["lines"][0]["result"]] == ["jackpot2"]


async def test_mega645_three_matches_is_g3():
    body = {"game": "mega645", "draw_date": "2026-11-12", "lines": [[45, 1, 2, 3, 6, 9]]}
    # trùng 03, 09, 45 = 3 số
    r = await post(full_db(), body)
    assert r.status_code == 200, r.text
    assert [x["code"] for x in r.json()["lines"][0]["result"]] == ["g3"]


async def test_multiple_xs_lines_mixed_win_and_lose_keep_order():
    r = await post(full_db(), xs_body(["00000", "12345", "67890", "11111", "91234"]))
    assert r.status_code == 200, r.text
    lines = r.json()["lines"]
    assert [x["numbers"] for x in lines] == [["00000"], ["12345"], ["67890"], ["11111"], ["91234"]]
    assert [codes(x) for x in lines] == [set(), {"db", "g7"}, {"g1"}, set(), {"g4"}]


async def test_multiple_mn_lines_mixed():
    r = await post(full_db(), xs_body(["123456", "000000", "906666"], province="tphcm"))
    lines = r.json()["lines"]
    assert [codes(x) for x in lines] == [{"db", "g2"}, set(), {"g6"}]


async def test_multiple_vietlott_lines_mixed():
    body = {"game": "power655", "draw_date": "2026-11-12",
            "lines": [[3, 9, 14, 27, 40, 55], [1, 2, 4, 5, 6, 8], [3, 9, 14, 20, 21, 22]]}
    r = await post(full_db(), body)
    assert r.status_code == 200, r.text
    got = [[x["code"] for x in l["result"]] for l in r.json()["lines"]]
    assert got == [["jackpot1"], [], ["g3"]]


async def test_max_lines_accepted_xs_5_vietlott_6():
    assert (await post(full_db(), xs_body(["12345"] * 5))).status_code == 200
    body = {"game": "mega645", "draw_date": "2026-11-12", "lines": [[1, 2, 3, 4, 5, 6]] * 6}
    assert (await post(full_db(), body)).status_code == 200


# ------------------------------------------------------------------ chưa có kết quả / không có kỳ
async def test_draw_without_current_version_not_published():
    db = full_db()
    db.draws[MB_ID] = _draw(MB_ID, "xs", "mb", "mb", None)
    r = await post(db, xs_body(["12345", "00000"]))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["published"] is False and j["draw"]["id"] == MB_ID
    assert [x["numbers"] for x in j["lines"]] == [["12345"], ["00000"]]
    assert all(x["result"] is None for x in j["lines"])
    assert not db.writes()


async def test_unknown_draw_404_draw_not_found():
    r = await post(FakeDB(), xs_body(["12345"]))
    assert r.status_code == 404
    assert "draw_not_found" in r.text


# ------------------------------------------------------------------ đầu vào sai
@pytest.mark.parametrize("lines", [["1234"], ["123456"], ["12a45"], [""], ["12345", "1234"]])
async def test_mb_bad_numbers_422_invalid_ticket(lines):
    r = await post(full_db(), xs_body(lines))
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text


@pytest.mark.parametrize("lines", [["12345"], ["1234567"], ["12345", "123456"]])
async def test_mn_requires_six_digits_422_invalid_ticket(lines):
    r = await post(full_db(), xs_body(lines, province="tphcm"))
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text


@pytest.mark.parametrize("game,line", [
    ("power655", [1, 1, 2, 3, 4, 5]),        # trùng số
    ("power655", [1, 2, 3, 4, 5]),           # thiếu số
    ("power655", [1, 2, 3, 4, 5, 56]),       # ngoài khoảng
    ("mega645", [1, 2, 3, 4, 5, 46]),
    ("mega645", [1, 2, 3, 4, 5, 6, 7]),
])
async def test_vietlott_bad_numbers_422_invalid_ticket(game, line):
    r = await post(full_db(), {"game": game, "draw_date": "2026-11-12", "lines": [line]})
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text


async def test_xs_missing_province_422_invalid_ticket():
    r = await post(full_db(), {"game": "xs", "draw_date": "2026-11-12", "lines": ["12345"]})
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text


async def test_xs_unknown_province_422_invalid_ticket():
    r = await post(full_db(), xs_body(["12345"], province="khongco"))
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text


@pytest.mark.parametrize("body", [
    {"game": "keno", "draw_date": "2026-11-12", "lines": [[1, 2, 3, 4, 5, 6]]},
    {"game": "xs", "province": "mb", "draw_date": "12/11/2026", "lines": ["12345"]},
    {"game": "xs", "province": "mb", "draw_date": "2026-13-45", "lines": ["12345"]},
    {"game": "xs", "province": "mb", "lines": ["12345"]},
    {"game": "xs", "province": "mb", "draw_date": "2026-11-12", "lines": []},
    {"game": "xs", "province": "mb", "draw_date": "2026-11-12", "lines": ["12345"] * 6},        # tối đa 5 vé xs
    {"game": "mega645", "draw_date": "2026-11-12", "lines": [[1, 2, 3, 4, 5, 6]] * 7},        # tối đa 6 dòng
    {"game": "xs", "province": "mb", "draw_date": "2026-11-12", "lines": "12345"},
    {"game": "xs", "province": "mb", "draw_date": "2026-11-12", "lines": [{"a": 1}]},
])
async def test_malformed_or_out_of_range_body_rejected_400_or_422(body):
    db = full_db()
    r = await post(db, body)
    assert r.status_code in (400, 422), r.text
    assert not db.writes()


# ------------------------------------------------------------------ giới hạn tần suất
async def test_rate_limit_30_per_minute_per_ip_then_429():
    db = full_db()
    async with cl(make_app(db), {"cf-connecting-ip": "1.2.3.4"}) as c:
        for i in range(30):
            r = await c.post("/v1/check-ticket", json=xs_body(["12345"]))
            assert r.status_code == 200, (i, r.text)
        r = await c.post("/v1/check-ticket", json=xs_body(["12345"]))
    assert r.status_code == 429, r.text
    assert "rate_limited" in r.text


async def test_rate_limit_is_per_ip():
    db = full_db()
    app = make_app(db)
    async with cl(app, {"cf-connecting-ip": "1.2.3.4"}) as a:
        for _ in range(30):
            await a.post("/v1/check-ticket", json=xs_body(["12345"]))
        assert (await a.post("/v1/check-ticket", json=xs_body(["12345"]))).status_code == 429
    async with cl(app, {"cf-connecting-ip": "5.6.7.8"}) as b:
        assert (await b.post("/v1/check-ticket", json=xs_body(["12345"]))).status_code == 200
