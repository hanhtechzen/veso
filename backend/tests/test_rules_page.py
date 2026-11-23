"""Trang /luat-choi: dữ liệu luật chơi hợp lệ và trang dựng được với CSDL giả (không mạng/Postgres)."""
from __future__ import annotations

from datetime import time

import httpx
from fastapi import FastAPI

from luckyvision.config import Settings
from luckyvision.domain import rules as R
from luckyvision.site import routes


def test_money_format():
    assert R.money(2_000_000_000) == "2 tỷ"
    assert R.money(500_000_000) == "500 triệu"
    assert R.money(1_200_000) == "1,2 triệu"
    assert R.money(40_000) == "40.000đ"


def test_rules_data_sane():
    anchors = [g["anchor"] for g in R.RULES]
    assert len(anchors) == len(set(anchors)) == 10
    assert set(anchors) == set(R.CHIP_LABELS)
    for g in R.RULES:
        assert g["prizes"], g["anchor"]
        for p in g["prizes"]:
            assert p["name"] and p["cond"] and p["value"], (g["anchor"], p)
        assert g["results"].startswith("/") and g["how"] and g["note"]
    assert R.UPDATED == "13/11/2026"
    assert all(u.startswith("https://www.vietlott.vn/") for _, u in R.SOURCES)


class Cur:
    def __init__(self, rows):
        self.rows = rows

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    async def execute(self, sql, params=None):
        rows = []
        if "FROM draw_schedules" in sql:
            for wd in range(1, 8):
                rows.append({"iso_weekday": wd, "draw_time": time(16, 15), "code": "tp-hcm", "name": "TP. Hồ Chí Minh", "region_code": "mn"})
                rows.append({"iso_weekday": wd, "draw_time": time(17, 15), "code": "da-nang", "name": "Đà Nẵng", "region_code": "mt"})
                rows.append({"iso_weekday": wd, "draw_time": time(18, 15), "code": "mb", "name": "Miền Bắc", "region_code": "mb"})
        return Cur(rows)


class FakePool:
    def connection(self):
        class CM:
            async def __aenter__(self_):
                return FakeDB()

            async def __aexit__(self_, *a):
                return False

        return CM()


async def test_rules_page_renders():
    app = FastAPI()
    app.include_router(routes.router)
    app.state.pool = FakePool()
    app.state.settings = Settings(_env_file=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/luat-choi")
    assert r.status_code == 200, r.text[:300]
    html = r.text
    assert "max-age=3600" in r.headers["cache-control"]
    assert "<h1>Luật chơi xổ số</h1>" in html
    for g in R.RULES:
        assert f'id="{g["anchor"]}"' in html
    assert 'href="/xs-tp-hcm"' in html and 'href="/xs-da-nang"' in html
    assert "2 tỷ" in html and "cập nhật 13/11/2026" in html
    assert 'href="/choi-thu.html"' in html and "FAQPage" in html


def test_subnav_has_rules_links():
    assert ("/luat-choi", "Luật chơi", "luat") in routes.SUBNAV["kq"]
    assert ("/luat-choi#vietlott", "Luật chơi", "luat") in routes.SUBNAV["vl"]
