"""Thống kê của tôi (chơi thử): domain/play_stats.py + GET /v1/play/stats + POST /v1/play/stats/ai.

Quy định: không dự đoán. AI chỉ nhận xét THÓI QUEN chơi; không gợi ý số, không hứa tăng cơ hội trúng.

Giả định cho coder:
  * api/play.py import `complete`, `AiError` từ ..ai (test monkeypatch `xs247.api.play.complete`, chữ ký như
    api/ai.py: complete(settings, http, system, user, max_tokens=...)); prompt do ai_prompt(stats) tạo phải là MỘT
    trong các đối số của complete (vị trí hoặc từ khóa).
  * Cài đặt lấy từ request.app.state.settings (settings.ai_enabled), như api/ai.py.
  * Hạn mức 3 lần/thành viên/ngày VN theo dõi TRONG TIẾN TRÌNH (dict cấp module), không qua DB (fake DB không lưu bảng mới).
    Mỗi test dùng một ngày VN riêng nên trạng thái module không rò giữa các test.
  * GET stats: SELECT từ play_tickets có tham số user_id (fake chỉ lọc khi thấy 7 trong tham số; nếu không, trả vé người khác).
  * Hàng vé: game, region_code, numbers, draw_date, cancelled_at, result, current_version (None), draw_id.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from xs247.api.errors import install
from xs247.auth import token_hash
from xs247.config import Settings

UTC = timezone.utc
CSRF = {"X-LV-CSRF": "1"}
MEMBER = {"Cookie": "lv_user=member", **CSRF}
G8 = [{"code": "g8", "name": "Giải tám"}]
G3 = [{"code": "g3", "name": "Giải ba"}]


def tk(game, numbers, day, region=None, result=None, cancelled=False):
    return {"game": game, "region": region, "numbers": numbers, "draw_date": day, "result": result,
            "cancelled_at": datetime(2026, 11, 9, 1, 0, tzinfo=UTC) if cancelled else None}


FIX = [
    tk("xs", ["12345"], date(2026, 11, 10), "mb", result=[]),
    tk("xs", ["000027"], date(2026, 11, 11), "mn", result=G8),
    tk("xs", ["99927"], date(2026, 11, 12), "mb"),
    tk("xs", ["12345"], date(2026, 11, 12), "mb"),                      # trùng vé đầu
    tk("power655", ["01", "02", "03", "04", "05", "40"], date(2026, 11, 12), result=G3),
    tk("mega645", ["10", "20", "32", "33", "40", "41"], date(2026, 11, 13)),
    tk("xs", ["27272"], date(2026, 11, 9), "mb", cancelled=True),       # đã hủy: bị loại hoàn toàn
]


# ------------------------------------------------------------------ domain thuần
def test_summarize_counts_exclude_cancelled():
    from xs247.domain.play_stats import summarize
    s = summarize(FIX)
    assert (s["total"], s["checked"], s["won"], s["pending"]) == (6, 3, 2, 3)
    assert s["by_game"] == {"xs": 4, "power655": 1, "mega645": 1}


def test_summarize_top_tail2_desc_count_then_asc_number():
    from xs247.domain.play_stats import summarize
    # đuôi: 45, 27, 27, 45 (vé hủy "27272" -> "72" không tính)
    assert summarize(FIX)["top_tail2"] == [{"number": "27", "count": 2}, {"number": "45", "count": 2}]


def test_summarize_top_tail2_max_five():
    from xs247.domain.play_stats import summarize
    t = [tk("xs", [f"1234{i}"], date(2026, 11, 10), "mb") for i in range(7)]
    got = summarize(t)["top_tail2"]
    assert [x["number"] for x in got] == ["40", "41", "42", "43", "44"]


def test_summarize_top_pick_counts_each_number_max_five():
    from xs247.domain.play_stats import summarize
    assert summarize(FIX)["top_pick"] == [{"number": "40", "count": 2}, {"number": "01", "count": 1},
                                          {"number": "02", "count": 1}, {"number": "03", "count": 1},
                                          {"number": "04", "count": 1}]


def test_summarize_repeat_rate_and_birthday_share():
    from xs247.domain.play_stats import summarize
    s = summarize(FIX)
    assert s["repeat_rate"] == 0.17            # 1/6
    assert s["birthday_share"] == 0.58         # 7 trên 12 số vietlott <= 31


def test_summarize_repeat_rate_three_identical():
    from xs247.domain.play_stats import summarize
    t = [tk("xs", ["12345"], date(2026, 11, 10 + i), "mb") for i in range(3)]
    assert summarize(t)["repeat_rate"] == 0.67


def test_summarize_repeat_rate_ignores_cancelled_original():
    from xs247.domain.play_stats import summarize
    t = [tk("xs", ["12345"], date(2026, 11, 9), "mb", cancelled=True), tk("xs", ["12345"], date(2026, 11, 10), "mb")]
    assert summarize(t)["repeat_rate"] == 0


def test_summarize_vietlott_same_set_is_repeat_regardless_of_order():
    from xs247.domain.play_stats import summarize
    a = tk("mega645", ["01", "02", "03", "04", "05", "06"], date(2026, 11, 10))
    b = tk("mega645", ["06", "05", "04", "03", "02", "01"], date(2026, 11, 11))
    assert summarize([a, b])["repeat_rate"] == 0.5


def test_summarize_prizes_and_expected_wins():
    from xs247.domain.play_stats import WIN_PROBABILITY, summarize
    assert {"xs_mb", "xs_mn", "xs_mt", "power655", "mega645", "lotto535", "max3d", "max3dpro"} == set(WIN_PROBABILITY)
    assert all(0 < v < 1 for v in WIN_PROBABILITY.values())
    s = summarize(FIX)
    assert s["prizes"] == {"g8": 1, "g3": 1}
    want = round(WIN_PROBABILITY["xs_mb"] + WIN_PROBABILITY["xs_mn"] + WIN_PROBABILITY["power655"], 3)
    assert s["expected_wins"] == want


def test_summarize_expected_wins_ignores_pending():
    from xs247.domain.play_stats import summarize
    assert summarize([tk("xs", ["12345"], date(2026, 11, 12), "mb")])["expected_wins"] == 0


def test_summarize_empty():
    from xs247.domain.play_stats import summarize
    s = summarize([])
    assert (s["total"], s["checked"], s["won"], s["pending"]) == (0, 0, 0, 0)
    assert s["by_game"] == {} and s["top_tail2"] == [] and s["top_pick"] == [] and s["prizes"] == {}
    assert s["repeat_rate"] == 0 and s["birthday_share"] is None and s["expected_wins"] == 0


def test_summarize_birthday_none_without_vietlott_and_all_cancelled():
    from xs247.domain.play_stats import summarize
    assert summarize([tk("xs", ["12345"], date(2026, 11, 10), "mb")])["birthday_share"] is None
    s = summarize([tk("power655", ["01", "02", "03", "04", "05", "06"], date(2026, 11, 10), cancelled=True)])
    assert s["total"] == 0 and s["birthday_share"] is None


def test_summarize_birthday_boundary_31_32():
    from xs247.domain.play_stats import summarize
    s = summarize([tk("mega645", ["01", "30", "31", "32", "33", "34"], date(2026, 11, 10))])
    assert s["birthday_share"] == 0.5


def test_ai_prompt_contains_numbers_and_legal_instructions():
    from xs247.domain.play_stats import ai_prompt, summarize
    p = ai_prompt(summarize(FIX))
    assert isinstance(p, str)
    assert "Không gợi ý số cụ thể" in p
    assert "không hứa hẹn tăng cơ hội trúng" in p
    for needle in ("6", "0.17", "0.58", "xs", "power655", "mega645"):
        assert needle in p, needle


@pytest.mark.parametrize("text,gone,kept", [
    ("Bạn hay chơi miền Bắc. Bạn nên thử chọn 27 và 45. Hãy chơi có chừng mực.", ["27", "45"],
     ["Bạn hay chơi miền Bắc.", "Hãy chơi có chừng mực."]),
    ("Nên chọn 05 17 hôm nay! Bạn chơi khá đều đặn.", ["05", "17"], ["Bạn chơi khá đều đặn."]),
    ("Bạn đã thử 123456 lần nữa. Chúc vui vẻ.", ["123456"], ["Chúc vui vẻ."]),
])
def test_sanitize_comment_removes_suggestion_sentences(text, gone, kept):
    from xs247.domain.play_stats import sanitize_comment
    out = sanitize_comment(text)
    assert isinstance(out, str)
    for g in gone:
        assert g not in out
    for k in kept:
        assert k in out


def test_sanitize_comment_keeps_harmless_text():
    from xs247.domain.play_stats import sanitize_comment
    t = "Bạn hay thử vận may mỗi tuần. Bạn thích chọn miền Bắc."
    assert sanitize_comment(t) == t


# ------------------------------------------------------------------ API
class Cur:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows if rows is not None else ([] if row is None else [row])

    async def fetchone(self):
        return self.row if self.row is not None else (self.rows[0] if self.rows else None)

    async def fetchall(self):
        return self.rows


def row(user, game, numbers, day, region=None, result=None, cancelled=False, id_=1):
    return {"id": id_, "user_id": user, "game": game, "region_code": region or ("vl" if game != "xs" else "mb"),
            "province_code": region or game, "numbers": numbers, "draw_date": day, "result": result,
            "checked_version": None, "current_version": None, "scheduled_at": None, "draw_status": "scheduled",
            "draw_id": f"x-{id_}", "created_at": datetime(2026, 11, 1, 3, 0, tzinfo=UTC),
            "cancelled_at": datetime(2026, 11, 2, 3, 0, tzinfo=UTC) if cancelled else None}


MINE = [row(7, "xs", ["12345"], date(2026, 11, 10), "mb", result=G8, id_=1),
        row(7, "xs", ["12345"], date(2026, 11, 11), "mb", result=[], id_=2),
        row(7, "power655", ["01", "02", "03", "04", "05", "40"], date(2026, 11, 12), id_=3),
        row(7, "xs", ["55555"], date(2026, 11, 9), "mb", cancelled=True, id_=4)]
OTHERS = [row(8, "mega645", ["10", "11", "12", "13", "14", "15"], date(2026, 11, 12), id_=10),
          row(8, "xs", ["77777"], date(2026, 11, 12), "mn", id_=11)]


class FakeDB:
    def __init__(self, tickets):
        self.tickets = tickets
        self.params: list[tuple] = []
        self.sessions = {token_hash("member"): {"id": 7, "display_name": "Thanh vien", "disabled": False}}

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        p = tuple(params or ())
        self.params.append(p)
        if "FROM user_sessions" in s:
            return Cur(self.sessions.get(p[0]))
        if "play_tickets" in s.lower() and s.lower().startswith("select"):
            rows = [t for t in self.tickets if t["user_id"] == 7] if 7 in p else list(self.tickets)
            return Cur(rows=[dict(t) for t in rows])
        return Cur()


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


@pytest.fixture
def calls():
    return []


def make_app(monkeypatch, calls, tickets=None, clock=None, key="k", reply="Bạn hay chơi đều đặn."):
    from xs247.api import play as play_api
    clock = clock or datetime(2026, 11, 20, 5, 0, tzinfo=UTC)
    monkeypatch.setattr(play_api, "now", lambda: clock)

    async def fake_complete(*a, **k):
        calls.append((a, k))
        return reply

    monkeypatch.setattr(play_api, "complete", fake_complete)
    db = FakeDB(MINE + OTHERS if tickets is None else tickets)
    a = FastAPI()
    install(a)
    a.include_router(play_api.router)
    a.state.pool = FakePool(db)
    a.state.settings = Settings(_env_file=None, ai_api_key=key, anthropic_api_key="", ai_requests_per_minute=10_000)
    a.state.collector = SimpleNamespace(http=None)
    a.state.db = db
    return a


def cl(app, headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers or {})


def set_clock(monkeypatch, clock):
    from xs247.api import play as play_api
    monkeypatch.setattr(play_api, "now", lambda: clock)


async def test_stats_requires_login(monkeypatch, calls):
    app = make_app(monkeypatch, calls)
    async with cl(app) as c:
        assert (await c.get("/v1/play/stats")).status_code == 401
        assert (await c.post("/v1/play/stats/ai", headers=CSRF)).status_code == 401
    assert calls == []


async def test_stats_only_own_tickets_and_private_no_store(monkeypatch, calls):
    from xs247.domain.play_stats import summarize
    app = make_app(monkeypatch, calls)
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/stats")
    assert r.status_code == 200, r.text
    cc = r.headers["cache-control"]
    assert "private" in cc and "no-store" in cc
    st = r.json()["stats"]
    assert st["total"] == 2 + 1                      # 3 vé của user 7 (vé hủy loại), không lẫn vé user 8
    assert st["by_game"] == {"xs": 2, "power655": 1}
    assert "mega645" not in st["by_game"]
    assert st == summarize([{"game": t["game"], "region": t["region_code"], "numbers": t["numbers"],
                             "draw_date": t["draw_date"], "cancelled_at": t["cancelled_at"], "result": t["result"]}
                            for t in MINE])
    assert any(7 in p for p in app.state.db.params if p != ())  # truy vấn có tham số user_id


async def test_stats_ai_requires_csrf(monkeypatch, calls):
    app = make_app(monkeypatch, calls)
    async with cl(app, {"Cookie": "lv_user=member"}) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 403 and calls == []


async def test_stats_ai_ok_uses_prompt_and_disclaimer(monkeypatch, calls):
    from xs247.domain.play_stats import ai_prompt, summarize
    app = make_app(monkeypatch, calls, clock=datetime(2026, 11, 21, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["comment"] == "Bạn hay chơi đều đặn."
    assert isinstance(j["disclaimer"], str) and j["disclaimer"]
    assert "no-store" in r.headers["cache-control"]
    assert len(calls) == 1
    a, k = calls[0]
    expected = ai_prompt(summarize([{"game": t["game"], "region": t["region_code"], "numbers": t["numbers"],
                                     "draw_date": t["draw_date"], "cancelled_at": t["cancelled_at"],
                                     "result": t["result"]} for t in MINE]))
    assert expected in list(a) + list(k.values())
    assert "Không gợi ý số cụ thể" in expected and "không hứa hẹn tăng cơ hội trúng" in expected


async def test_stats_ai_returns_sanitized_comment(monkeypatch, calls):
    reply = "Bạn hay chơi miền Bắc. Bạn nên thử chọn 27 và 45. Hãy chơi có chừng mực."
    app = make_app(monkeypatch, calls, reply=reply, clock=datetime(2026, 11, 22, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 200
    out = r.json()["comment"]
    assert "27" not in out and "45" not in out
    assert "Bạn hay chơi miền Bắc." in out and "Hãy chơi có chừng mực." in out


async def test_stats_ai_disabled_503(monkeypatch, calls):
    app = make_app(monkeypatch, calls, key="", clock=datetime(2026, 11, 23, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 503 and "ai_disabled" in r.text
    assert calls == []


async def test_stats_ai_not_enough_tickets_422_without_calling_ai(monkeypatch, calls):
    few = [MINE[0], MINE[1], MINE[3]]    # 2 vé còn hiệu lực + 1 vé hủy
    app = make_app(monkeypatch, calls, tickets=few, clock=datetime(2026, 11, 24, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 422 and "not_enough_tickets" in r.text
    assert calls == []


async def test_stats_ai_exactly_three_tickets_allowed(monkeypatch, calls):
    app = make_app(monkeypatch, calls, tickets=MINE, clock=datetime(2026, 11, 25, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/stats/ai")
    assert r.status_code == 200 and len(calls) == 1


async def test_stats_ai_daily_limit_3_then_429_then_next_vn_day(monkeypatch, calls):
    app = make_app(monkeypatch, calls, clock=datetime(2026, 11, 26, 5, 0, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        for _ in range(3):
            assert (await c.post("/v1/play/stats/ai")).status_code == 200
        r = await c.post("/v1/play/stats/ai")
        assert r.status_code == 429 and "ai_daily_limit" in r.text
        assert len(calls) == 3                       # lần 4 không gọi AI
        set_clock(monkeypatch, datetime(2026, 11, 27, 5, 0, tzinfo=UTC))
        assert (await c.post("/v1/play/stats/ai")).status_code == 200


async def test_stats_ai_daily_limit_uses_vietnam_midnight(monkeypatch, calls):
    # 23:30 VN ngày 28 = 16:30 UTC ngày 28; 00:30 VN ngày 29 = 17:30 UTC ngày 28
    app = make_app(monkeypatch, calls, clock=datetime(2026, 11, 28, 16, 30, tzinfo=UTC))
    async with cl(app, MEMBER) as c:
        for _ in range(3):
            assert (await c.post("/v1/play/stats/ai")).status_code == 200
        assert (await c.post("/v1/play/stats/ai")).status_code == 429
        set_clock(monkeypatch, datetime(2026, 11, 28, 17, 30, tzinfo=UTC))   # đã sang ngày VN mới
        assert (await c.post("/v1/play/stats/ai")).status_code == 200
