"""Chơi thử: luật dò vé (domain/play.py) và API /v1/play/* (api/play.py).

Phần API dùng FakeDB dispatch theo từ khóa SQL (không Postgres thật). Giả định về hình dạng SQL (lỏng, theo từ khóa):
  * mọi câu có "FROM user_sessions" -> phiên thành viên (cookie lv_user=member, user id 7).
  * câu chứa "play_tickets":
      - INSERT ...           -> thêm vé, RETURNING * (hàng vé; tham số: user_id, game, tỉnh, draw_id, số... theo thứ tự tùy ý)
      - SELECT ... count(    -> đếm vé của user trong ngày. Fake nhận cả hai kiểu tham số: một `date` (ngày VN) hoặc
                               khoảng [datetime đầu, datetime cuối) (mốc 00:00 VN). Đếm cả vé đã hủy.
      - SELECT ...           -> vé (đã JOIN lottery_draws): fake trả hàng vé + trường kỳ quay: scheduled_at, current_version,
                               status, region_code, province_code, draw_date, game. Lọc theo user_id / id nếu có trong tham số.
                               Cột vé: id, user_id, game, province_code, draw_id, draw_date, numbers, result, checked_version,
                               created_at, cancelled_at.
      - UPDATE ... result    -> ghi kết quả dò (UPDATE play_tickets SET result=..., checked_version=...)
      - UPDATE ... cancel / DELETE -> hủy vé (xóa hẳn hoặc đặt cancelled_at đều được)
  * "FROM lottery_results" -> các hàng {draw_id, prize_code, number, position} của phiên bản hiện hành.
  * "FROM lottery_draws"/"draw_versions" -> hàng kỳ quay {id, game, region_code, province_code, draw_date, scheduled_at,
                               current_version, status}; fetchall cũng trả [hàng đó].
  * "FROM provinces" -> {code, name, region_code, game, active}.
Số kỳ xs: id 'mb-mb-2026-11-12' (quay 18:15 VN, đóng 18:00). Power 6/55: 'vl-power655-2026-11-12' (18:00, đóng 17:30).
Đồng hồ: monkeypatch `xs247.api.play.now()` (aware datetime).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from xs247.api.errors import install
from xs247.auth import token_hash
from xs247.config import VN_TZ

CSRF = {"X-LV-CSRF": "1"}
MEMBER = {"Cookie": "lv_user=member", **CSRF}
UTC = timezone.utc


# ------------------------------------------------------------------ domain thuần
MB = {"db": ["12345"], "g1": ["67890"], "g4": ["1234", "5678"], "g7": ["45", "99", "05"]}
MN = {"db": ["123456"], "g1": ["78901"], "g2": ["23456"], "g3": ["11111", "22222"], "g4": ["33333"],
      "g5": ["4444"], "g6": ["5555", "6666", "7777"], "g7": ["888"], "g8": ["12"]}


def test_check_trad_mb_special_and_last2():
    from xs247.domain.play import check_trad
    assert set(check_trad("mb", "12345", MB)) == {"db", "g7"}


def test_check_trad_mb_special_needs_all_five_digits():
    from xs247.domain.play import check_trad
    assert check_trad("mb", "02345", MB) == ["g7", "kk"]   # trùng 2 số cuối "45": Giải Bảy + Khuyến khích (2 số cuối ĐB)
    assert "db" not in check_trad("mb", "12346", MB)


def test_check_trad_mb_g1_and_none():
    from xs247.domain.play import check_trad
    assert check_trad("mb", "67890", MB) == ["g1"]
    assert check_trad("mb", "00000", MB) == []


def test_check_trad_mb_keeps_leading_zeros():
    from xs247.domain.play import check_trad
    assert check_trad("mb", "00005", MB) == ["g7"]


def test_check_trad_mb_last4_prize():
    from xs247.domain.play import check_trad
    assert set(check_trad("mb", "91234", MB)) == {"g4"}


def test_check_trad_mn_db_and_g2_not_phu_db_or_kk():
    from xs247.domain.play import check_trad
    got = check_trad("mn", "123456", MN)
    assert set(got) == {"db", "g2"}


def test_check_trad_mn_multiple_numbers_same_prize():
    from xs247.domain.play import check_trad
    assert check_trad("mt", "922222", MN) == ["g3"]
    assert check_trad("mt", "911111", MN) == ["g3"]


def test_check_trad_mn_g6_last4_and_g8_last2():
    from xs247.domain.play import check_trad
    assert set(check_trad("mn", "906666", MN)) == {"g6"}
    assert set(check_trad("mn", "900012", MN)) == {"g8"}
    assert set(check_trad("mn", "900888", MN)) == {"g7"}


def test_check_trad_mn_phu_db():
    from xs247.domain.play import check_trad
    assert set(check_trad("mn", "023456", MN)) == {"g2", "phu_db"}
    assert set(check_trad("mn", "923456", MN)) == {"g2", "phu_db"}


def test_check_trad_mn_khuyen_khich():
    from xs247.domain.play import check_trad
    assert check_trad("mn", "123450", MN) == ["kk"]      # đúng chữ số đầu, sai đúng 1 trong 5 số còn lại
    assert check_trad("mn", "153456", MN) == ["kk"]


def test_check_trad_mn_kk_not_when_two_digits_differ_or_first_differs():
    from xs247.domain.play import check_trad
    assert check_trad("mn", "123400", MN) == []
    assert check_trad("mn", "190456", MN) == []
    assert "kk" not in check_trad("mn", "223450", MN)


def test_check_trad_mn_no_prize():
    from xs247.domain.play import check_trad
    assert check_trad("mn", "000000", MN) == []


P655 = {"main": [3, 9, 14, 27, 40, 55], "special": [7]}
P655_STR = {"main": ["03", "09", "14", "27", "40", "55"], "special": ["07"]}
M645 = {"main": [3, 9, 14, 27, 40, 45]}


def test_check_pick_power655_levels():
    from xs247.domain.play import check_pick
    assert check_pick("power655", [3, 9, 14, 27, 40, 55], P655) == "jackpot1"
    assert check_pick("power655", [3, 9, 14, 27, 40, 7], P655) == "jackpot2"
    assert check_pick("power655", [3, 9, 14, 27, 40, 8], P655) == "g1"
    assert check_pick("power655", [3, 9, 14, 27, 1, 8], P655) == "g2"
    assert check_pick("power655", [3, 9, 14, 2, 1, 8], P655) == "g3"
    assert check_pick("power655", [3, 9, 20, 2, 1, 8], P655) is None


def test_check_pick_power655_special_alone_does_not_count():
    from xs247.domain.play import check_pick
    assert check_pick("power655", [3, 9, 7, 2, 1, 8], P655) is None   # 2 trùng + số đặc biệt
    assert check_pick("power655", [3, 9, 14, 7, 1, 8], P655) == "g3"  # 3 trùng chính; số ĐB không nâng hạng


def test_check_pick_accepts_string_prizes():
    from xs247.domain.play import check_pick
    assert check_pick("power655", [3, 9, 14, 27, 40, 7], P655_STR) == "jackpot2"
    assert check_pick("power655", [3, 9, 14, 27, 40, 55], P655_STR) == "jackpot1"


def test_check_pick_mega645_levels():
    from xs247.domain.play import check_pick
    assert check_pick("mega645", [3, 9, 14, 27, 40, 45], M645) == "jackpot"
    assert check_pick("mega645", [3, 9, 14, 27, 40, 1], M645) == "g1"
    assert check_pick("mega645", [3, 9, 14, 27, 2, 1], M645) == "g2"
    assert check_pick("mega645", [3, 9, 14, 6, 2, 1], M645) == "g3"
    assert check_pick("mega645", [3, 9, 15, 6, 2, 1], M645) is None
    assert check_pick("mega645", [3, 9, 14, 27, 40, 45], {"main": ["03", "09", "14", "27", "40", "45"]}) == "jackpot"


def test_prize_names_cover_codes():
    from xs247.domain.play import PRIZE_NAMES
    for code in ("db", "g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "phu_db", "kk", "jackpot", "jackpot1", "jackpot2"):
        assert isinstance(PRIZE_NAMES.get(code), str) and PRIZE_NAMES[code], code


@pytest.mark.parametrize("region,nums,expected", [
    ("mb", ["12345"], ["12345"]),
    ("mn", ["012345"], ["012345"]),
    ("mt", ["000000"], ["000000"]),
])
def test_validate_ticket_xs_ok(region, nums, expected):
    from xs247.domain.play import validate_ticket
    assert validate_ticket("xs", region, nums) == expected


@pytest.mark.parametrize("region,nums", [
    ("mb", ["1234"]), ("mb", ["123456"]), ("mn", ["12345"]), ("mn", ["1234567"]),
    ("mb", ["12a45"]), ("mb", []), ("mb", ["12345", "67890"]), ("mn", [""]), ("mb", [12345]),
])
def test_validate_ticket_xs_bad(region, nums):
    from xs247.domain.play import validate_ticket
    with pytest.raises(ValueError):
        validate_ticket("xs", region, nums)


def test_validate_ticket_vietlott_sorted_padded():
    from xs247.domain.play import validate_ticket
    assert validate_ticket("power655", "", [55, 1, 3, 20, 9, 14]) == ["01", "03", "09", "14", "20", "55"]
    assert validate_ticket("mega645", "", [45, 1, 2, 3, 4, 5]) == ["01", "02", "03", "04", "05", "45"]


@pytest.mark.parametrize("game,nums", [
    ("power655", [1, 2, 3, 4, 5]), ("power655", [1, 2, 3, 4, 5, 5]), ("power655", [0, 1, 2, 3, 4, 5]),
    ("power655", [1, 2, 3, 4, 5, 56]), ("power655", [1, 2, 3, 4, 5, 6, 7]),
    ("mega645", [1, 2, 3, 4, 5, 46]), ("mega645", [1, 2, 3, 4, 5, 5]), ("mega645", [-1, 2, 3, 4, 5, 6]),
])
def test_validate_ticket_vietlott_bad(game, nums):
    from xs247.domain.play import validate_ticket
    with pytest.raises(ValueError):
        validate_ticket(game, "", nums)


def test_closes_at_xs_15_minutes_vietlott_30():
    from xs247.domain.play import closes_at
    d = datetime(2026, 11, 12, 18, 15, tzinfo=VN_TZ)
    assert closes_at(d, "xs") == datetime(2026, 11, 12, 18, 0, tzinfo=VN_TZ)
    d2 = datetime(2026, 11, 12, 18, 0, tzinfo=VN_TZ)
    assert closes_at(d2, "power655") == datetime(2026, 11, 12, 17, 30, tzinfo=VN_TZ)
    assert closes_at(d2, "mega645") == datetime(2026, 11, 12, 17, 30, tzinfo=VN_TZ)


# ------------------------------------------------------------------ API
class Cur:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows if rows is not None else ([] if row is None else [row])
        self.rowcount = len(self.rows)

    async def fetchone(self):
        return self.row if self.row is not None else (self.rows[0] if self.rows else None)

    async def fetchall(self):
        return self.rows


class CountRow(dict):
    """Hàng đếm: khóa nào cũng trả số đếm (n/count/c...), chỉ số 0 cũng được."""

    def __init__(self, n):
        super().__init__(n=n)
        self.n = n

    def __getitem__(self, k):
        return self.n


def ticket(id_, user=7, created=None, game="xs", draw_id="mb-mb-2026-11-12", numbers=None, result=None,
           checked_version=None, cancelled=False):
    return {"id": id_, "user_id": user, "game": game, "province_code": draw_id.split("-")[1] if "-" in draw_id else "mb",
            "draw_id": draw_id, "draw_date": date(2026, 11, 12), "numbers": numbers or ["12345"], "result": result,
            "checked_version": checked_version, "created_at": created or datetime(2026, 11, 10, 3, 0, tzinfo=UTC),
            "cancelled_at": datetime(2026, 11, 10, 4, 0, tzinfo=UTC) if cancelled else None}


def xs_draw(version=None, scheduled=None):
    return {"id": "mb-mb-2026-11-12", "game": "xs", "region_code": "mb", "province_code": "mb",
            "draw_date": date(2026, 11, 12), "scheduled_at": scheduled or datetime(2026, 11, 12, 18, 15, tzinfo=VN_TZ),
            "current_version": version, "status": "published" if version else "scheduled"}


class FakeDB:
    def __init__(self, draw=None, tickets=None, results=None):
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.draw = draw if draw is not None else xs_draw()
        self.tickets = list(tickets or [])
        self.results = results or {}      # version -> list[(prize_code, number)]
        self.next_id = 500
        self.updates: list[tuple[str, tuple]] = []
        self.sessions = {token_hash("member"): {"id": 7, "display_name": "Thanh vien", "disabled": False}}
        self.provinces = {"code": "mb", "name": "Miền Bắc", "region_code": "mb", "game": "xs", "active": True}

    def _joined(self, t):
        d = {k: v for k, v in self.draw.items() if k != "id"}
        return {**t, **d}

    def alive(self):
        return [t for t in self.tickets if not t.get("cancelled_at")]

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        p = tuple(params or ())
        self.sql.append(s)
        self.params.append(p)
        low = s.lower()
        if "FROM user_sessions" in s:
            return Cur(self.sessions.get(p[0]))
        if "play_tickets" in low:
            return self._tickets(s, low, p)
        if "lottery_results" in low:
            ver = self.draw.get("current_version")
            return Cur(rows=[{"draw_id": self.draw["id"], "prize_code": c, "number": n, "position": i}
                             for i, (c, n) in enumerate(self.results.get(ver, []))])
        if "from provinces" in low:
            return Cur(self.provinces)
        if "lottery_draws" in low or "draw_versions" in low:
            return Cur(self.draw) if self.draw else Cur()
        return Cur()

    def _tickets(self, s, low, p):
        if low.startswith("insert"):
            strs = [x for x in p if isinstance(x, str)]
            lists = [x for x in p if isinstance(x, list)]
            row = ticket(self.next_id, user=7, game=next((x for x in strs if x in ("xs", "power655", "mega645")), "xs"),
                         draw_id=next((x for x in strs if x.count("-") >= 3), self.draw["id"]),
                         numbers=lists[0] if lists else ["12345"], created=datetime.now(UTC))
            self.next_id += 1
            self.tickets.append(row)
            return Cur(row)
        if low.startswith("update") or low.startswith("delete"):
            self.updates.append((s, p))
            ids = [t["id"] for t in self.tickets if t["id"] in p]
            for t in self.tickets:
                if t["id"] in ids:
                    if low.startswith("delete"):
                        t["_deleted"] = True
                        t["cancelled_at"] = datetime.now(UTC)
                    elif "cancel" in low:
                        t["cancelled_at"] = datetime.now(UTC)
                    elif "checked_version" in low:
                        t["checked_version"] = self.draw.get("current_version")
                        t["_result_written"] = True
            c = Cur(rows=[{"id": i} for i in ids])
            c.rowcount = len(ids)
            return c
        if "count(" in low:
            mine = [t for t in self.tickets if t["user_id"] == 7]
            dates = [x for x in p if type(x) is date]
            dts = [x for x in p if isinstance(x, datetime)]
            if dates:
                mine = [t for t in mine if t["created_at"].astimezone(VN_TZ).date() == dates[0]]
            elif len(dts) >= 2:
                lo, hi = min(dts), max(dts)
                mine = [t for t in mine if lo <= t["created_at"] < hi]
            return Cur(CountRow(len(mine)))
        rows = list(self.tickets)
        ids = [x for x in p if x in {t["id"] for t in rows}]
        if ids:
            rows = [t for t in rows if t["id"] in ids]
        if 7 in p:
            rows = [t for t in rows if t["user_id"] == 7]
        rows = [t for t in rows if not t.get("cancelled_at") or "cancelled_at is null" not in low]
        return Cur(rows=[self._joined(t) for t in rows])


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


def make_app(monkeypatch, db, clock):
    from xs247.api import play as play_api
    monkeypatch.setattr(play_api, "now", lambda: clock)
    a = FastAPI()
    install(a)
    a.include_router(play_api.router)
    a.state.pool = FakePool(db)
    a.state.collector = SimpleNamespace(http=None)
    return a


def cl(app, headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers or {})


NOW_OPEN = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)     # 12:00 VN ngày 10
BODY_MB = {"game": "xs", "province": "mb", "draw_date": "2026-11-12", "numbers": ["12345"]}


async def test_play_endpoints_require_login():
    from xs247.api import play as play_api  # noqa: F401
    app = FastAPI()
    install(app)
    app.include_router(play_api.router)
    app.state.pool = FakePool(FakeDB())
    async with cl(app) as c:
        assert (await c.get("/v1/play/tickets")).status_code == 401
        assert (await c.get("/v1/play/draws")).status_code == 401
        assert (await c.post("/v1/play/tickets", json=BODY_MB, headers=CSRF)).status_code == 401
        assert (await c.delete("/v1/play/tickets/1", headers=CSRF)).status_code == 401


async def test_create_ticket_requires_csrf(monkeypatch):
    db = FakeDB()
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, {"Cookie": "lv_user=member"}) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
        d = await c.delete("/v1/play/tickets/101")
    assert r.status_code == 403 and d.status_code == 403
    assert not db.tickets


async def test_create_ticket_ok_201_no_store(monkeypatch):
    db = FakeDB()
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 201, r.text
    assert "ticket" in r.json() and r.json()["ticket"]["id"]
    assert "no-store" in r.headers["cache-control"] and "private" in r.headers["cache-control"]
    assert len(db.tickets) == 1


@pytest.mark.parametrize("body", [
    {**BODY_MB, "numbers": ["1234"]},
    {**BODY_MB, "numbers": ["12a45"]},
    {**BODY_MB, "numbers": []},
    {"game": "power655", "draw_date": "2026-11-12", "numbers": [1, 2, 3, 4, 5, 5]},
    {"game": "mega645", "draw_date": "2026-11-12", "numbers": [1, 2, 3, 4, 5, 46]},
])
async def test_create_ticket_bad_numbers_422_invalid_ticket(monkeypatch, body):
    db = FakeDB()
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=body)
    assert r.status_code == 422, r.text
    assert "invalid_ticket" in r.text
    assert not db.tickets


async def test_create_ticket_closed_after_close_time(monkeypatch):
    # đóng lúc 18:00 VN (= 11:00 UTC): đúng 18:00 đã đóng
    db = FakeDB()
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 11, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 422 and "draw_closed" in r.text
    assert not db.tickets


async def test_create_ticket_open_one_second_before_close(monkeypatch):
    db = FakeDB()
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 10, 59, 59, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 201, r.text


async def test_create_ticket_closed_when_draw_already_published(monkeypatch):
    db = FakeDB(draw=xs_draw(version=1))
    app = make_app(monkeypatch, db, NOW_OPEN)   # chưa tới giờ nhưng kỳ đã có kết quả
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 422 and "draw_closed" in r.text


async def test_create_ticket_vietlott_closes_30_minutes_before(monkeypatch):
    draw = {"id": "vl-power655-2026-11-12", "game": "power655", "region_code": "vl", "province_code": "power655",
            "draw_date": date(2026, 11, 12), "scheduled_at": datetime(2026, 11, 12, 18, 0, tzinfo=VN_TZ),
            "current_version": None, "status": "scheduled"}
    body = {"game": "power655", "draw_date": "2026-11-12", "numbers": [1, 2, 3, 4, 5, 6]}
    db = FakeDB(draw=draw)
    # 17:35 VN: xs-quy tắc 15 phút sẽ còn mở, vietlott phải đã đóng
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 10, 35, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=body)
    assert r.status_code == 422 and "draw_closed" in r.text


async def test_daily_limit_429_after_10_including_cancelled(monkeypatch):
    base = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)   # 10:00 VN ngày 10
    tk = [ticket(100 + i, created=base + timedelta(minutes=i), cancelled=(i < 3)) for i in range(10)]
    db = FakeDB(tickets=tk)
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 429 and "daily_limit" in r.text
    assert len(db.tickets) == 10


async def test_daily_limit_nine_tickets_still_allowed(monkeypatch):
    base = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)
    db = FakeDB(tickets=[ticket(100 + i, created=base) for i in range(9)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 201, r.text


async def test_daily_limit_uses_vietnam_date_early_morning_counts_as_same_day(monkeypatch):
    # 10 vé lúc 00:30 VN ngày 10 (= 17:30 UTC ngày 9); bây giờ 12:00 VN ngày 10 (05:00 UTC ngày 10).
    # Nếu dùng ngày UTC sẽ đếm 0 và cho tạo thêm -> phải 429.
    created = datetime(2026, 11, 9, 17, 30, tzinfo=UTC)
    db = FakeDB(tickets=[ticket(100 + i, created=created) for i in range(10)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 429 and "daily_limit" in r.text


async def test_daily_limit_resets_at_vietnam_midnight(monkeypatch):
    # 10 vé lúc 23:30 VN ngày 10 (= 16:30 UTC ngày 10); bây giờ 00:30 VN ngày 11 (= 17:30 UTC ngày 10) -> ngày mới, được tạo.
    created = datetime(2026, 11, 10, 16, 30, tzinfo=UTC)
    db = FakeDB(tickets=[ticket(100 + i, created=created) for i in range(10)])
    app = make_app(monkeypatch, db, datetime(2026, 11, 10, 17, 30, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=BODY_MB)
    assert r.status_code == 201, r.text


async def test_list_tickets_checks_lazily_and_stores(monkeypatch):
    from xs247.domain.play import PRIZE_NAMES
    tk = [ticket(101, numbers=["12345"])]
    db = FakeDB(draw=xs_draw(version=1), tickets=tk, results={1: [("db", "12345"), ("g1", "67890"), ("g7", "45")]})
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 13, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/tickets")
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"]
    items = r.json()["tickets"]
    assert len(items) == 1
    codes = {x["code"]: x["name"] for x in items[0]["result"]}
    assert set(codes) == {"db", "g7"} and codes["db"].startswith(PRIZE_NAMES["db"])
    assert any(u[0].lower().startswith("update") and "play_tickets" in u[0] and "result" in u[0].lower()
               for u in db.updates)
    assert tk[0].get("_result_written")


async def test_list_tickets_losing_ticket_has_empty_result(monkeypatch):
    tk = [ticket(101, numbers=["00000"])]
    db = FakeDB(draw=xs_draw(version=1), tickets=tk, results={1: [("db", "12345")]})
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 13, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert items[0]["result"] == []


async def test_list_tickets_pending_draw_has_no_result_and_no_update(monkeypatch):
    db = FakeDB(draw=xs_draw(version=None), tickets=[ticket(101)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert items[0]["result"] is None
    assert not db.updates


async def test_list_tickets_not_rechecked_when_version_unchanged(monkeypatch):
    stored = [{"code": "db", "name": "Giải Đặc biệt"}]
    db = FakeDB(draw=xs_draw(version=2), tickets=[ticket(101, result=stored, checked_version=2)],
                results={2: [("db", "12345")]})
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 13, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert [x["code"] for x in items[0]["result"]] == ["db"]
    assert not db.updates


async def test_list_tickets_rechecked_when_current_version_changes(monkeypatch):
    old = [{"code": "db", "name": "Giải Đặc biệt"}]
    tk = [ticket(101, numbers=["12345"], result=old, checked_version=1)]
    # bản đính chính v2: ĐB đổi thành 99999 -> vé không còn trúng ĐB
    db = FakeDB(draw=xs_draw(version=2), tickets=tk, results={2: [("db", "99999"), ("g7", "45")]})
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 13, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert [x["code"] for x in items[0]["result"]] == ["g7"]
    assert db.updates and tk[0]["checked_version"] == 2


async def test_list_tickets_only_own(monkeypatch):
    db = FakeDB(tickets=[ticket(101), ticket(102, user=8)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert [t["id"] for t in items] == [101]


async def test_list_tickets_vietlott_check(monkeypatch):
    draw = {"id": "vl-power655-2026-11-12", "game": "power655", "region_code": "vl", "province_code": "power655",
            "draw_date": date(2026, 11, 12), "scheduled_at": datetime(2026, 11, 12, 18, 0, tzinfo=VN_TZ),
            "current_version": 1, "status": "published"}
    t = ticket(101, game="power655", draw_id="vl-power655-2026-11-12", numbers=["03", "09", "14", "27", "40", "07"])
    res = {1: [("main", n) for n in ("03", "09", "14", "27", "40", "55")] + [("special", "07")]}
    db = FakeDB(draw=draw, tickets=[t], results=res)
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 13, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        items = (await c.get("/v1/play/tickets")).json()["tickets"]
    assert [x["code"] for x in items[0]["result"]] == ["jackpot2"]


async def test_delete_own_ticket_before_close(monkeypatch):
    db = FakeDB(tickets=[ticket(101)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.delete("/v1/play/tickets/101")
    assert r.status_code in (200, 204), r.text
    assert db.tickets[0].get("cancelled_at") or db.tickets[0].get("_deleted")


async def test_delete_after_close_422_draw_closed(monkeypatch):
    db = FakeDB(tickets=[ticket(101)])
    app = make_app(monkeypatch, db, datetime(2026, 11, 12, 11, 5, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.delete("/v1/play/tickets/101")
    assert r.status_code == 422 and "draw_closed" in r.text
    assert not db.tickets[0].get("cancelled_at")


async def test_delete_other_users_ticket_404(monkeypatch):
    db = FakeDB(tickets=[ticket(102, user=8)])
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.delete("/v1/play/tickets/102")
    assert r.status_code == 404
    assert not db.tickets[0].get("cancelled_at")


async def test_delete_missing_ticket_404(monkeypatch):
    db = FakeDB()
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.delete("/v1/play/tickets/999")
    assert r.status_code == 404


async def test_draws_lists_open_and_remaining_today(monkeypatch):
    base = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)
    db = FakeDB(tickets=[ticket(100 + i, created=base) for i in range(3)] +
                        [ticket(200, created=datetime(2026, 11, 9, 3, 0, tzinfo=UTC))])  # hôm qua: không tính
    app = make_app(monkeypatch, db, NOW_OPEN)
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/draws")
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"]
    j = r.json()
    assert j["remaining_today"] == 7
    assert isinstance(j["draws"], list)
