"""Dò vé công khai cho Lotto 5/35 (2 kỳ/ngày, chọn kỳ theo giờ), Max 3D, Max 3D Pro: dò đủ mọi hạng giải."""
from __future__ import annotations

from datetime import date

import pytest

from test_check_ticket import DAY, Cur, FakeDB, _draw, cl, make_app

L1 = "lotto-lotto535-2026-11-12-01001"
L2 = "lotto-lotto535-2026-11-12-01002"
M3 = "max3d-max3d-2026-11-12"
MP = "max3dpro-max3dpro-2026-11-12"
LOTTO_13 = {"main": ["01", "05", "18", "26", "33"], "special": ["07"]}
LOTTO_21 = {"main": ["04", "08", "12", "21", "26"], "special": ["05"]}
M3P = {"db": ["131", "822"], "g1": ["251", "636", "626", "985"], "g2": ["687", "454", "353", "550", "096", "427"],
       "g3": ["854", "831", "941", "083", "053", "785", "542", "308"]}


class MoreDB(FakeDB):
    async def execute(self, sql, params=None):
        low = " ".join(sql.split()).lower()
        if "lottery_draws" in low and "lotto535" in low:
            self.sql.append(low)
            rows = [dict(d, draw_seq=int(i[-5:])) for i, d in self.draws.items() if i.startswith("lotto-")]
            return Cur(rows)
        return await super().execute(sql, params)


def db():
    draws = {L2: _draw(L2, "lotto535", "lotto", "lotto535", 1), L1: _draw(L1, "lotto535", "lotto", "lotto535", 1),
             M3: _draw(M3, "max3d", "max3d", "max3d", 1), MP: _draw(MP, "max3dpro", "max3dpro", "max3dpro", 1)}
    return MoreDB(draws, {L1: LOTTO_13, L2: LOTTO_21, M3: M3P, MP: M3P})


async def post(d, body):
    async with cl(make_app(d)) as c:
        return await c.post("/v1/check-ticket", json=body)


def codes(r):
    return [[x["code"] for x in ln["result"]] for ln in r.json()["lines"]]


@pytest.mark.asyncio
async def test_lotto_slot_picks_right_draw_and_all_tiers():
    lines = [[1, 5, 18, 26, 33, 7], [1, 5, 18, 26, 33, 9], [1, 5, 18, 26, 30, 7], [1, 5, 18, 2, 3, 7],
             [1, 5, 2, 3, 4, 7], [1, 2, 3, 4, 6, 7], [2, 3, 4, 6, 9, 10]]
    r = await post(db(), {"game": "lotto535", "draw_date": DAY.isoformat(), "slot": "13:00", "lines": lines[:6]})
    assert r.status_code == 200 and r.json()["published"]
    assert r.json()["draw"]["id"] == L1
    got = codes(r)
    assert got[0] == ["dd"] and got[1] and got[2] and got[3] and got[4]
    assert all(g for g in got[:5])
    r2 = await post(db(), {"game": "lotto535", "draw_date": DAY.isoformat(), "slot": "21:00", "lines": [[4, 8, 12, 21, 26, 5]]})
    assert r2.json()["draw"]["id"] == L2 and codes(r2) == [["dd"]]


@pytest.mark.asyncio
async def test_lotto_needs_slot():
    r = await post(db(), {"game": "lotto535", "draw_date": DAY.isoformat(), "lines": [[1, 2, 3, 4, 5, 6]]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_max3d_every_group():
    r = await post(db(), {"game": "max3d", "draw_date": DAY.isoformat(), "lines": ["131", "985", "096", "308", "000"]})
    assert r.status_code == 200
    assert codes(r) == [["db"], ["g1"], ["g2"], ["g3"], []]


@pytest.mark.asyncio
async def test_max3dpro_tiers():
    r = await post(db(), {"game": "max3dpro", "draw_date": DAY.isoformat(),
                          "lines": [["131", "822"], ["822", "131"], ["251", "636"], ["131", "000"], ["000", "111"]]})
    assert r.status_code == 200
    got = codes(r)
    assert "db" in got[0] and "pdb" in got[1] and "g1" in got[2] and "g5" in got[3] and got[4] == []


@pytest.mark.asyncio
async def test_lotto_past_day_without_draw_is_not_found():
    r = await post(MoreDB(), {"game": "lotto535", "draw_date": date(2020, 1, 1).isoformat(), "slot": "13:00",
                              "lines": [[1, 2, 3, 4, 5, 6]]})
    assert r.status_code == 404
