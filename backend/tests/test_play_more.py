"""Chơi thử mở rộng: Lotto 5/35 (2 kỳ/ngày, có "slot"), Max 3D, Max 3D Pro.

Domain thuần (luckyvision.domain.play), helper luckyvision.play_service.resolve_lotto_draw và API /v1/play/*.
Dùng lại FakeDB/make_app của test_play.py; MoreDB bên dưới bổ sung: lịch quay (draw_schedules), kỳ quay theo id,
các kỳ Lotto đã công bố trong ngày (câu SELECT lottery_draws có "draw_seq"), kết quả theo kỳ (lottery_results).

Quy ước (theo đặc tả):
  * Lotto: 6 giá trị, giá trị cuối là số đặc biệt (1..12); lưu 5 số chính sắp xếp + số ĐB, đệm 0.
  * Mã kỳ Lotto của vé: 'lotto-lotto535-YYYY-MM-DD@1300' / '@2100'.
  * Vé Lotto được dò với kỳ đã công bố trong ngày theo thứ tự draw_seq (đầu = 13:00, thứ hai = 21:00).
Ngày cố định: 2026-11-10 là thứ Ba (Max3D: T2/T4/T6; Max3D Pro: T3/T5/T7).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

import pytest

from luckyvision.config import VN_TZ
from test_play import (BODY_MB, CSRF, MEMBER, NOW_OPEN, Cur, FakeDB, cl, make_app, ticket)  # noqa: F401

UTC = timezone.utc


# ------------------------------------------------------------------ validate_ticket
@pytest.mark.parametrize("nums,expected", [
    ([3, 9, 14, 27, 35, 8], ["03", "09", "14", "27", "35", "08"]),
    ([35, 27, 14, 9, 3, 12], ["03", "09", "14", "27", "35", "12"]),      # 5 số chính được sắp xếp, số ĐB vẫn đứng cuối
    ([1, 2, 3, 4, 5, 1], ["01", "02", "03", "04", "05", "01"]),          # biên thấp nhất
    ([31, 32, 33, 34, 35, 12], ["31", "32", "33", "34", "35", "12"]),    # biên cao nhất
    ([3, 9, 12, 14, 27, 12], ["03", "09", "12", "14", "27", "12"]),      # số ĐB được trùng một số chính (lồng cầu riêng)
])
def test_validate_ticket_lotto535_ok(nums, expected):
    from luckyvision.domain.play import validate_ticket
    assert validate_ticket("lotto535", "lotto", nums) == expected


@pytest.mark.parametrize("nums", [
    [], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6, 7],      # sai số lượng (cần đúng 6 giá trị)
    [1, 2, 3, 4, 4, 8],                              # trùng số chính
    [0, 2, 3, 4, 5, 8], [1, 2, 3, 4, 36, 8],         # số chính ngoài 1..35
    [1, 2, 3, 4, 5, 0], [1, 2, 3, 4, 5, 13],         # số ĐB ngoài 1..12
    [-1, 2, 3, 4, 5, 8],
])
def test_validate_ticket_lotto535_bad(nums):
    from luckyvision.domain.play import validate_ticket
    with pytest.raises(ValueError):
        validate_ticket("lotto535", "lotto", nums)


@pytest.mark.parametrize("nums", [["000"], ["007"], ["123"], ["999"]])
def test_validate_ticket_max3d_ok_keeps_leading_zeros(nums):
    from luckyvision.domain.play import validate_ticket
    assert validate_ticket("max3d", "max3d", nums) == nums


@pytest.mark.parametrize("nums", [
    [], ["12"], ["1234"], [123], ["12a"], ["-12"], [""], ["123", "456"], [" 12"],
])
def test_validate_ticket_max3d_bad(nums):
    from luckyvision.domain.play import validate_ticket
    with pytest.raises(ValueError):
        validate_ticket("max3d", "max3d", nums)


@pytest.mark.parametrize("nums", [["123", "456"], ["456", "123"], ["123", "123"], ["000", "999"]])
def test_validate_ticket_max3dpro_ok_keeps_order_and_equal(nums):
    from luckyvision.domain.play import validate_ticket
    assert validate_ticket("max3dpro", "max3dpro", nums) == nums      # thứ tự có nghĩa: không sắp xếp


@pytest.mark.parametrize("nums", [
    [], ["123"], ["123", "45"], ["123", "456", "789"], [123, 456], ["12a", "456"], ["123", ""],
])
def test_validate_ticket_max3dpro_bad(nums):
    from luckyvision.domain.play import validate_ticket
    with pytest.raises(ValueError):
        validate_ticket("max3dpro", "max3dpro", nums)


# ------------------------------------------------------------------ check_ticket
L535 = {"main": ["03", "09", "14", "27", "35"], "special": ["08"]}


@pytest.mark.parametrize("nums,code", [
    (["03", "09", "14", "27", "35", "08"], "dd"),     # 5 chính + ĐB
    (["03", "09", "14", "27", "35", "07"], "g1"),     # 5 chính
    (["03", "09", "14", "27", "30", "08"], "g2"),     # 4 chính + ĐB
    (["03", "09", "14", "27", "30", "07"], "g3"),     # 4 chính
    (["03", "09", "14", "20", "30", "08"], "g4"),     # 3 chính + ĐB
    (["03", "09", "14", "20", "30", "07"], "g5"),     # 3 chính
    (["01", "02", "04", "20", "30", "08"], "kk"),     # chỉ trúng ĐB
    (["03", "09", "04", "20", "30", "08"], "kk"),     # 2 chính + ĐB: vẫn chỉ khuyến khích
    (["03", "09", "04", "20", "30", "07"], None),     # 2 chính, không ĐB
    (["01", "02", "04", "20", "30", "07"], None),
])
def test_check_ticket_lotto535_levels(nums, code):
    from luckyvision.domain.play import PRIZE_NAMES, check_ticket
    got = check_ticket("lotto535", "lotto", nums, L535)
    if code is None:
        assert got == []
    else:
        assert got == [{"code": code, "name": PRIZE_NAMES[code]}]


def test_check_ticket_lotto535_special_number_is_not_matched_against_main():
    from luckyvision.domain.play import check_ticket
    # số ĐB của vé (35) trùng một số chính của kỳ nhưng ĐB của kỳ là 08: không được tính là trúng ĐB / số chính
    got = check_ticket("lotto535", "lotto", ["01", "02", "04", "20", "30", "12"], {"main": ["03", "09", "14", "27", "12"], "special": ["08"]})
    assert got == []
    got = check_ticket("lotto535", "lotto", ["03", "09", "14", "27", "12", "08"], {"main": ["03", "09", "14", "27", "35"], "special": ["08"]})
    assert [x["code"] for x in got] == ["g2"]       # 4 chính (không tính 12) + ĐB


M3D = {"db": ["123", "456"], "g1": ["111", "222", "333", "444"], "g2": ["100", "200", "300", "400", "500", "600"],
       "g3": ["010", "020", "030", "040", "050", "060", "070", "080"]}


@pytest.mark.parametrize("num,codes", [
    ("123", {"db"}), ("456", {"db"}), ("111", {"g1"}), ("444", {"g1"}), ("100", {"g2"}), ("600", {"g2"}),
    ("010", {"g3"}), ("080", {"g3"}), ("999", set()), ("000", set()),
])
def test_check_ticket_max3d_groups(num, codes):
    from luckyvision.domain.play import PRIZE_NAMES, check_ticket
    got = check_ticket("max3d", "max3d", [num], M3D)
    assert {x["code"] for x in got} == codes and len(got) == len(codes)
    assert all(x["name"] == PRIZE_NAMES[x["code"]] for x in got)


def test_check_ticket_max3d_number_wins_every_group_containing_it():
    from luckyvision.domain.play import check_ticket
    pr = {"db": ["123", "456"], "g1": ["123", "222", "333", "444"], "g2": ["100", "200", "123", "400", "500", "600"],
          "g3": ["010", "020", "030", "040", "050", "060", "070", "123"]}
    assert {x["code"] for x in check_ticket("max3d", "max3d", ["123"], pr)} == {"db", "g1", "g2", "g3"}


def test_check_ticket_max3d_does_not_match_by_suffix():
    from luckyvision.domain.play import check_ticket
    assert check_ticket("max3d", "max3d", ["010"], {"db": ["10"], "g1": ["110"], "g2": [], "g3": []}) == []


P3 = {"db": ["123", "456"], "g1": ["111", "222", "333", "444"], "g2": ["100", "200", "300", "400", "500", "600"],
      "g3": ["010", "020", "030", "040", "050", "060", "070", "080"]}


@pytest.mark.parametrize("pair,codes", [
    (("123", "456"), {"db", "g4", "g5"}),            # đúng thứ tự ĐB1, ĐB2
    (("456", "123"), {"pdb", "g4", "g5"}),           # đảo thứ tự: Phụ đặc biệt
    (("111", "222"), {"g1", "g4", "g6"}),            # cả hai cùng nhóm G1
    (("111", "111"), {"g1", "g4", "g6"}),            # hai số trùng nhau: một lần xuất hiện trong G1 là đủ
    (("100", "200"), {"g2", "g4", "g6"}),
    (("600", "600"), {"g2", "g4", "g6"}),
    (("010", "080"), {"g3", "g4", "g6"}),
    (("070", "070"), {"g3", "g4", "g6"}),
    (("111", "100"), {"g4", "g6"}),                  # khác nhóm: không G1/G2, nhưng cả hai thuộc 20 số
    (("123", "111"), {"g4", "g5", "g6"}),            # a thuộc ĐB, b thuộc G1
    (("111", "999"), {"g6"}),                        # chỉ một số thuộc G1..G3
    (("123", "999"), {"g5"}),                        # chỉ một số thuộc ĐB
    (("999", "888"), set()),
    (("123", "123"), {"g4", "g5"}),                  # trùng một số ĐB nhưng không đúng cặp ĐB1/ĐB2
])
def test_check_ticket_max3dpro_levels(pair, codes):
    from luckyvision.domain.play import PRIZE_NAMES, check_ticket
    got = check_ticket("max3dpro", "max3dpro", list(pair), P3)
    assert {x["code"] for x in got} == codes and len(got) == len(codes)
    assert all(x["name"] == PRIZE_NAMES[x["code"]] for x in got)


def test_check_ticket_max3dpro_equal_special_numbers_is_db_not_pdb():
    from luckyvision.domain.play import check_ticket
    pr = {**P3, "db": ["777", "777"]}
    got = {x["code"] for x in check_ticket("max3dpro", "max3dpro", ["777", "777"], pr)}
    assert "db" in got and "pdb" not in got


def test_check_ticket_max3dpro_pdb_needs_swapped_order_only_when_db_differ():
    from luckyvision.domain.play import check_ticket
    pr = {**P3, "db": ["777", "777"]}
    assert "pdb" not in {x["code"] for x in check_ticket("max3dpro", "max3dpro", ["777", "999"], pr)}


def test_check_ticket_max3dpro_g1_needs_both_numbers_in_g1():
    from luckyvision.domain.play import check_ticket
    got = {x["code"] for x in check_ticket("max3dpro", "max3dpro", ["333", "123"], P3)}
    assert "g1" not in got and {"g4", "g5", "g6"} <= got


# ------------------------------------------------------------------ PRIZE_NAMES, closes_at
def test_prize_names_cover_new_codes():
    from luckyvision.domain.play import PRIZE_NAMES
    for code in ("dd", "g1", "g2", "g3", "g4", "g5", "g6", "pdb", "kk", "db"):
        assert isinstance(PRIZE_NAMES.get(code), str) and PRIZE_NAMES[code].strip(), code
    assert PRIZE_NAMES["dd"] == "Độc đắc"
    assert PRIZE_NAMES["pdb"] != PRIZE_NAMES["db"] and "phụ" in PRIZE_NAMES["pdb"].lower()
    assert PRIZE_NAMES["db"] == "Giải Đặc biệt" and PRIZE_NAMES["g1"] == "Giải Nhất"
    assert PRIZE_NAMES["kk"] == "Giải Khuyến khích"


@pytest.mark.parametrize("game", ["lotto535", "max3d", "max3dpro"])
def test_closes_at_new_games_30_minutes_before(game):
    from luckyvision.domain.play import closes_at
    assert closes_at(datetime(2026, 11, 12, 21, 0, tzinfo=VN_TZ), game) == datetime(2026, 11, 12, 20, 30, tzinfo=VN_TZ)
    assert closes_at(datetime(2026, 11, 12, 13, 0, tzinfo=VN_TZ), game) == datetime(2026, 11, 12, 12, 30, tzinfo=VN_TZ)


# ------------------------------------------------------------------ resolve_lotto_draw
def _row(id_, seq):
    return {"id": id_, "draw_seq": seq, "current_version": 1}


def test_resolve_lotto_draw_first_is_1300_second_is_2100():
    from luckyvision.play_service import resolve_lotto_draw
    a, b = _row("lotto-lotto535-2026-11-12-00101", 101), _row("lotto-lotto535-2026-11-12-00102", 102)
    assert resolve_lotto_draw([a, b], "13:00")["id"] == a["id"]
    assert resolve_lotto_draw([a, b], "21:00")["id"] == b["id"]


def test_resolve_lotto_draw_orders_by_draw_seq_not_by_input_order():
    from luckyvision.play_service import resolve_lotto_draw
    a, b = _row("A", 101), _row("B", 102)
    assert resolve_lotto_draw([b, a], "13:00")["id"] == "A"
    assert resolve_lotto_draw([b, a], "21:00")["id"] == "B"


def test_resolve_lotto_draw_only_first_published_yet():
    from luckyvision.play_service import resolve_lotto_draw
    a = _row("A", 101)
    assert resolve_lotto_draw([a], "13:00")["id"] == "A"
    assert resolve_lotto_draw([a], "21:00") is None


def test_resolve_lotto_draw_nothing_published():
    from luckyvision.play_service import resolve_lotto_draw
    assert resolve_lotto_draw([], "13:00") is None
    assert resolve_lotto_draw([], "21:00") is None


def test_resolve_lotto_draw_does_not_mutate_input():
    from luckyvision.play_service import resolve_lotto_draw
    rows = [_row("B", 102), _row("A", 101)]
    resolve_lotto_draw(rows, "13:00")
    assert [r["id"] for r in rows] == ["B", "A"]


# ------------------------------------------------------------------ API
def _sched(code, weekdays, region=None):
    return [{"province_code": code, "province_name": code, "draw_time": time(18, 0), "region_code": region or code,
             "game": code, "iso_weekday": w} for w in weekdays]


SCHEDULES = _sched("max3d", (1, 3, 5)) + _sched("max3dpro", (2, 4, 6))
_ALL_GAMES = ("xs", "power655", "mega645", "lotto535", "max3d", "max3dpro")


class MoreDB(FakeDB):
    """FakeDB + lịch quay, kỳ theo id, kỳ Lotto đã công bố trong ngày, kết quả theo kỳ."""

    def __init__(self, tickets=None, schedules=None, draws_by_id=None, lotto_rows=None, results_by_draw=None):
        super().__init__(draw={}, tickets=tickets)
        self.schedules = SCHEDULES if schedules is None else schedules
        self.draws_by_id = draws_by_id or {}
        self.lotto_rows = lotto_rows or []
        self.results_by_draw = results_by_draw or {}

    def _joined(self, t):
        d = self.draws_by_id.get(t["draw_id"])
        if d:
            return {**t, **{k: v for k, v in d.items() if k != "id"}}
        return {**t, "scheduled_at": None, "current_version": None, "status": None}

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        p = tuple(params or ())
        low = s.lower()
        if "FROM user_sessions" in s:
            return await super().execute(sql, params)
        if "draw_schedules" in low:
            self.sql.append(s), self.params.append(p)
            return Cur(rows=[dict(r) for r in self.schedules if r["iso_weekday"] == p[0]])
        if "play_tickets" in low and low.startswith("insert"):
            self.sql.append(s), self.params.append(p)
            strs = [x for x in p if isinstance(x, str)]
            row = ticket(self.next_id, user=7, game=next(x for x in strs if x in _ALL_GAMES),
                         draw_id=next(x for x in strs if re.search(r"\d{4}-\d{2}-\d{2}", x)),
                         numbers=next(x for x in p if isinstance(x, list)), created=datetime.now(UTC))
            row["draw_date"] = next((x for x in p if type(x) is date), row["draw_date"])
            row["region_code"] = next((x for x in strs if x in ("lotto", "max3d", "max3dpro", "xs")), None)
            self.next_id += 1
            self.tickets.append(row)
            return Cur(row)
        if "play_tickets" in low:
            return await super().execute(sql, params)
        if "lottery_results" in low:
            self.sql.append(s), self.params.append(p)
            ids = list(p[0]) if p and isinstance(p[0], (list, tuple)) else list(p)
            return Cur(rows=[{"draw_id": i, "prize_code": c, "number": n, "position": k}
                             for i in ids for k, (c, n) in enumerate(self.results_by_draw.get(i, []))])
        if "lottery_draws" in low:
            self.sql.append(s), self.params.append(p)
            if any(isinstance(x, str) and "@" in x for x in p):
                return Cur()
            if "draw_seq" in low:
                days = [x for x in p if type(x) is date]
                rows = [r for r in self.lotto_rows if not days or r["draw_date"] in days]
                return Cur(rows=[dict(r) for r in rows])
            if "between" in low:
                return Cur(rows=[])
            d = next((self.draws_by_id[x] for x in p if isinstance(x, str) and x in self.draws_by_id), None)
            return Cur(d) if d else Cur()
        return await super().execute(sql, params)


def _vn(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=VN_TZ)


async def _get_draws(monkeypatch, now):
    db = MoreDB()
    app = make_app(monkeypatch, db, now)
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/draws")
    assert r.status_code == 200, r.text
    return r.json()["draws"]


async def test_open_draws_include_both_lotto_slots_each_day(monkeypatch):
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 11, 0))      # 11:00 VN thứ Ba: cả 2 kỳ hôm nay còn mở
    lotto = [d for d in draws if d["game"] == "lotto535"]
    assert len(lotto) == 14                                              # 7 ngày x 2 kỳ
    by = {(d["draw_date"], d["slot"]): d for d in lotto}
    for i in range(7):
        day = date(2026, 11, 10) + timedelta(days=i)
        for slot, hh in (("13:00", 13), ("21:00", 21)):
            d = by[(day.isoformat(), slot)]
            sched = _vn(day.year, day.month, day.day, hh)
            assert datetime.fromisoformat(d["scheduled_at"]) == sched
            assert datetime.fromisoformat(d["closes_at"]) == sched - timedelta(minutes=30)
            assert d["id"] == f"lotto-lotto535-{day.isoformat()}@{slot.replace(':', '')}"


async def test_open_draws_lotto_slot_that_has_closed_is_dropped(monkeypatch):
    # 12:30 VN đúng giờ đóng kỳ 13:00 (đóng lúc 12:30: now >= close là đã đóng); kỳ 21:00 vẫn mở
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 12, 30))
    lotto_today = [d for d in draws if d["game"] == "lotto535" and d["draw_date"] == "2026-11-10"]
    assert [d["slot"] for d in lotto_today] == ["21:00"]
    assert len([d for d in draws if d["game"] == "lotto535"]) == 13


async def test_open_draws_lotto_slot_open_one_minute_before_close(monkeypatch):
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 12, 29))
    assert [d["slot"] for d in draws if d["game"] == "lotto535" and d["draw_date"] == "2026-11-10"] == ["13:00", "21:00"]


async def test_open_draws_lotto_after_2100_close_only_future_days(monkeypatch):
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 20, 31))
    assert not [d for d in draws if d["game"] == "lotto535" and d["draw_date"] == "2026-11-10"]
    assert len([d for d in draws if d["game"] == "lotto535"]) == 12


async def test_open_draws_max3d_and_max3dpro_one_per_scheduled_day(monkeypatch):
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 12, 30))
    m3d = [d for d in draws if d["game"] == "max3d"]
    pro = [d for d in draws if d["game"] == "max3dpro"]
    assert [d["draw_date"] for d in m3d] == ["2026-11-11", "2026-11-13", "2026-11-16"]       # T4, T6, T2
    assert [d["draw_date"] for d in pro] == ["2026-11-10", "2026-11-12", "2026-11-14"]       # T3, T5, T7
    for d in m3d + pro:
        day = date.fromisoformat(d["draw_date"])
        assert datetime.fromisoformat(d["scheduled_at"]) == _vn(day.year, day.month, day.day, 18)
        assert datetime.fromisoformat(d["closes_at"]) == _vn(day.year, day.month, day.day, 17, 30)
        assert d["id"] == f"{d['game']}-{d['game']}-{d['draw_date']}"
        assert "slot" not in d or d["slot"] is None


async def test_open_draws_max3dpro_closed_today_after_1730(monkeypatch):
    draws = await _get_draws(monkeypatch, _vn(2026, 11, 10, 17, 30))
    assert "2026-11-10" not in [d["draw_date"] for d in draws if d["game"] == "max3dpro"]


LOTTO_BODY = {"game": "lotto535", "draw_date": "2026-11-12", "slot": "21:00", "numbers": [3, 9, 14, 27, 35, 8]}


async def _post(monkeypatch, body, now=NOW_OPEN, db=None):
    db = db if db is not None else MoreDB()
    app = make_app(monkeypatch, db, now)
    async with cl(app, MEMBER) as c:
        r = await c.post("/v1/play/tickets", json=body)
    return r, db


@pytest.mark.parametrize("slot,suffix", [("13:00", "1300"), ("21:00", "2100")])
async def test_post_lotto_ok_stores_stable_draw_id(monkeypatch, slot, suffix):
    r, db = await _post(monkeypatch, {**LOTTO_BODY, "slot": slot})
    assert r.status_code == 201, r.text
    t = r.json()["ticket"]
    assert t["game"] == "lotto535"
    assert t["draw_id"] == f"lotto-lotto535-2026-11-12@{suffix}"
    assert t["numbers"] == ["03", "09", "14", "27", "35", "08"]
    assert db.tickets[0]["draw_id"] == f"lotto-lotto535-2026-11-12@{suffix}"
    assert db.tickets[0]["numbers"] == ["03", "09", "14", "27", "35", "08"]


async def test_post_lotto_missing_slot_422_invalid_ticket(monkeypatch):
    body = {k: v for k, v in LOTTO_BODY.items() if k != "slot"}
    r, db = await _post(monkeypatch, body)
    assert r.status_code == 422 and "invalid_ticket" in r.text
    assert not db.tickets


@pytest.mark.parametrize("slot", ["14:00", "1300", "", None, "21:00:00"])
async def test_post_lotto_invalid_slot_422_invalid_ticket(monkeypatch, slot):
    r, db = await _post(monkeypatch, {**LOTTO_BODY, "slot": slot})
    assert r.status_code == 422 and "invalid_ticket" in r.text
    assert not db.tickets


@pytest.mark.parametrize("nums", [[3, 9, 14, 27, 35], [3, 9, 14, 27, 27, 8], [3, 9, 14, 27, 36, 8], [3, 9, 14, 27, 35, 13]])
async def test_post_lotto_bad_numbers_422_invalid_ticket(monkeypatch, nums):
    r, db = await _post(monkeypatch, {**LOTTO_BODY, "numbers": nums})
    assert r.status_code == 422 and "invalid_ticket" in r.text
    assert not db.tickets


async def test_post_lotto_slot_closed_30_minutes_before(monkeypatch):
    now = _vn(2026, 11, 12, 12, 30)       # kỳ 13:00 đóng đúng 12:30
    r, db = await _post(monkeypatch, {**LOTTO_BODY, "slot": "13:00"}, now=now)
    assert r.status_code == 422 and "draw_closed" in r.text and not db.tickets
    r2, db2 = await _post(monkeypatch, {**LOTTO_BODY, "slot": "21:00"}, now=now)
    assert r2.status_code == 201, r2.text
    assert db2.tickets[0]["draw_id"] == "lotto-lotto535-2026-11-12@2100"


async def test_post_lotto_beyond_horizon_422_draw_not_found(monkeypatch):
    r, db = await _post(monkeypatch, {**LOTTO_BODY, "draw_date": "2026-11-20"})
    assert r.status_code == 422 and "draw_not_found" in r.text and not db.tickets


def _pro_draw(version=None):
    return {"id": "max3dpro-max3dpro-2026-11-12", "game": "max3dpro", "region_code": "max3dpro",
            "province_code": "max3dpro", "draw_date": date(2026, 11, 12), "scheduled_at": _vn(2026, 11, 12, 18),
            "current_version": version, "status": "published" if version else "scheduled"}


async def test_post_max3dpro_ok_201(monkeypatch):
    db = MoreDB(draws_by_id={"max3dpro-max3dpro-2026-11-12": _pro_draw()})
    body = {"game": "max3dpro", "draw_date": "2026-11-12", "numbers": ["123", "456"]}
    r, db = await _post(monkeypatch, body, db=db)
    assert r.status_code == 201, r.text
    t = r.json()["ticket"]
    assert t["game"] == "max3dpro" and t["numbers"] == ["123", "456"]
    assert t["draw_id"] == "max3dpro-max3dpro-2026-11-12"
    assert datetime.fromisoformat(t["closes_at"]) == _vn(2026, 11, 12, 17, 30)
    assert len(db.tickets) == 1


async def test_post_max3dpro_closed_at_1730(monkeypatch):
    db = MoreDB(draws_by_id={"max3dpro-max3dpro-2026-11-12": _pro_draw()})
    body = {"game": "max3dpro", "draw_date": "2026-11-12", "numbers": ["123", "456"]}
    r, db = await _post(monkeypatch, body, now=_vn(2026, 11, 12, 17, 30), db=db)
    assert r.status_code == 422 and "draw_closed" in r.text and not db.tickets


@pytest.mark.parametrize("nums", [["123"], ["123", "45"], ["123", "456", "789"], [123, 456]])
async def test_post_max3dpro_bad_numbers_422(monkeypatch, nums):
    body = {"game": "max3dpro", "draw_date": "2026-11-12", "numbers": nums}
    r, db = await _post(monkeypatch, body)
    assert r.status_code == 422 and "invalid_ticket" in r.text and not db.tickets


async def test_post_max3d_ok_201_keeps_leading_zeros(monkeypatch):
    draw = {**_pro_draw(), "id": "max3d-max3d-2026-11-13", "game": "max3d", "region_code": "max3d",
            "province_code": "max3d", "draw_date": date(2026, 11, 13), "scheduled_at": _vn(2026, 11, 13, 18)}
    db = MoreDB(draws_by_id={draw["id"]: draw})
    r, db = await _post(monkeypatch, {"game": "max3d", "draw_date": "2026-11-13", "numbers": ["007"]}, db=db)
    assert r.status_code == 201, r.text
    assert r.json()["ticket"]["numbers"] == ["007"]
    assert r.json()["ticket"]["draw_id"] == "max3d-max3d-2026-11-13"


# ---- dò vé lười khi liệt kê
def _tk(id_, game, region, draw_id, day, numbers):
    t = ticket(id_, game=game, draw_id=draw_id, numbers=numbers)
    t["draw_date"] = day
    t["region_code"] = region
    return t


def _lotto_rows():
    # cố ý để kỳ thứ hai đứng trước: phải xếp theo draw_seq
    return [
        {"id": "lotto-lotto535-2026-11-12-00102", "game": "lotto535", "draw_date": date(2026, 11, 12), "draw_seq": 102,
         "current_version": 1, "status": "published", "scheduled_at": _vn(2026, 11, 12, 21)},
        {"id": "lotto-lotto535-2026-11-12-00101", "game": "lotto535", "draw_date": date(2026, 11, 12), "draw_seq": 101,
         "current_version": 1, "status": "published", "scheduled_at": _vn(2026, 11, 12, 13)},
    ]


def _lotto_results():
    return {
        "lotto-lotto535-2026-11-12-00101": [("main", n) for n in ("03", "09", "14", "27", "30")] + [("special", "01")],
        "lotto-lotto535-2026-11-12-00102": [("main", n) for n in ("03", "09", "14", "27", "35")] + [("special", "08")],
    }


async def test_list_tickets_lazily_checks_lotto_ticket_resolved_by_slot(monkeypatch):
    nums = ["03", "09", "14", "27", "35", "08"]
    tk = [_tk(101, "lotto535", "lotto", "lotto-lotto535-2026-11-12@1300", date(2026, 11, 12), nums),
          _tk(102, "lotto535", "lotto", "lotto-lotto535-2026-11-12@2100", date(2026, 11, 12), nums)]
    db = MoreDB(tickets=tk, lotto_rows=_lotto_rows(), results_by_draw=_lotto_results())
    app = make_app(monkeypatch, db, _vn(2026, 11, 12, 22))
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/tickets")
    assert r.status_code == 200, r.text
    items = {x["id"]: x for x in r.json()["tickets"]}
    from luckyvision.domain.play import PRIZE_NAMES
    # 13:00 -> kỳ 101: 03 09 14 27 trùng (4 chính), ĐB 01 != 08 -> g3
    assert items[101]["result"] == [{"code": "g3", "name": PRIZE_NAMES["g3"]}]
    # 21:00 -> kỳ 102: 5 chính + ĐB -> Độc đắc
    assert items[102]["result"] == [{"code": "dd", "name": "Độc đắc"}]
    assert items[101]["checked_version"] == 1 and items[102]["checked_version"] == 1
    assert any(u[0].lower().startswith("update") and "play_tickets" in u[0] for u in db.updates)


async def test_list_tickets_lotto_slot_not_yet_published_stays_pending(monkeypatch):
    nums = ["03", "09", "14", "27", "35", "08"]
    tk = [_tk(101, "lotto535", "lotto", "lotto-lotto535-2026-11-12@1300", date(2026, 11, 12), nums),
          _tk(102, "lotto535", "lotto", "lotto-lotto535-2026-11-12@2100", date(2026, 11, 12), nums)]
    rows = [r for r in _lotto_rows() if r["draw_seq"] == 101]            # mới có kỳ 13:00
    db = MoreDB(tickets=tk, lotto_rows=rows, results_by_draw=_lotto_results())
    app = make_app(monkeypatch, db, _vn(2026, 11, 12, 15))
    async with cl(app, MEMBER) as c:
        items = {x["id"]: x for x in (await c.get("/v1/play/tickets")).json()["tickets"]}
    assert items[101]["result"] == [{"code": "g3", "name": "Giải Ba"}]
    assert items[102]["result"] is None and items[102]["checked_version"] is None


async def test_list_tickets_lazily_checks_max3d_ticket(monkeypatch):
    from luckyvision.domain.play import PRIZE_NAMES
    did = "max3d-max3d-2026-11-13"
    draw = {"id": did, "game": "max3d", "region_code": "max3d", "province_code": "max3d", "draw_date": date(2026, 11, 13),
            "scheduled_at": _vn(2026, 11, 13, 18), "current_version": 1, "status": "published"}
    res = [("db", "123"), ("db", "456")] + [("g1", n) for n in ("111", "222", "333", "444")] \
        + [("g2", n) for n in ("100", "200", "300", "400", "500", "007")] + [("g3", n) for n in ("010", "020", "030", "040", "050", "060", "070", "123")]
    tk = [_tk(101, "max3d", "max3d", did, date(2026, 11, 13), ["123"]),      # ĐB và G3
          _tk(102, "max3d", "max3d", did, date(2026, 11, 13), ["007"]),      # G2 (giữ số 0 đầu)
          _tk(103, "max3d", "max3d", did, date(2026, 11, 13), ["999"])]
    db = MoreDB(tickets=tk, draws_by_id={did: draw}, results_by_draw={did: res})
    app = make_app(monkeypatch, db, _vn(2026, 11, 13, 20))
    async with cl(app, MEMBER) as c:
        r = await c.get("/v1/play/tickets")
    assert r.status_code == 200, r.text
    items = {x["id"]: x for x in r.json()["tickets"]}
    assert {x["code"]: x["name"] for x in items[101]["result"]} == {"db": PRIZE_NAMES["db"], "g3": PRIZE_NAMES["g3"]}
    assert [x["code"] for x in items[102]["result"]] == ["g2"]
    assert items[103]["result"] == []
    assert all(items[i]["checked_version"] == 1 for i in (101, 102, 103))
    assert any(u[0].lower().startswith("update") and "result" in u[0].lower() for u in db.updates)
