"""Quy định: không công khai dự đoán xổ số. Chỉ vai trò "admin" dùng được:
POST /v1/ai/pick, GET /v1/predictions/board, PUT /v1/user/predictions.

Không dùng mạng/Postgres thật: FakeDB trả hàng theo từ khóa SQL; phiên đăng nhập giả lập qua giá trị cookie
(lv_session = viewer | editor | admin; lv_user = member). Token Bearer cấu hình qua ADMIN_TOKENS.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from xs247.api import admin, ai as ai_api, tools
from xs247.api.errors import install
from xs247.auth import token_hash
from xs247.config import Settings

TOK = {"viewer": "v" * 32, "editor": "e" * 32, "admin": "a" * 32}
CSRF = {"X-LV-CSRF": "1"}


class Cur:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows if rows is not None else ([] if row is None else [row])

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


def _admin_row(role):
    return {"id": 1, "username": role, "display_name": role, "role": role, "must_change_pw": False,
            "totp_enabled": False, "active": True}


class FakeDB:
    def __init__(self):
        self.sql: list[str] = []
        self.admin_sessions = {token_hash(r): _admin_row(r) for r in ("viewer", "editor", "admin")}
        self.user_sessions = {token_hash("member"): {"id": 7, "display_name": "Thanh vien", "disabled": False}}

    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.sql.append(s)
        if "FROM admin_sessions" in s:
            return Cur(self.admin_sessions.get(params[0]))
        if "FROM user_sessions" in s:
            return Cur(self.user_sessions.get(params[0]))
        if "FROM user_prediction_docs p JOIN users" in s:
            return Cur(rows=[{"id": 7, "display_name": "Thanh vien", "doc": {"entries": {}, "lo": {}}}])
        if s.startswith("SELECT doc FROM user_prediction_docs"):
            return Cur(None)
        if "max(draw_seq)" in s:
            return Cur({"s": 5})
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
def app(monkeypatch):
    settings = Settings(_env_file=None, ai_api_key="k", ai_requests_per_minute=10_000,
                        admin_tokens=",".join(f"{t}:{r}:{r}" for r, t in TOK.items()))
    monkeypatch.setattr(admin, "get_settings", lambda: settings)

    async def fake_ctx(conn, region, province):
        return {"hot_last_30": [], "longest_gaps": [], "draws_analyzed": 0}

    async def fake_complete(*a, **k):
        return "x"

    monkeypatch.setattr(ai_api, "stats_context", fake_ctx)
    monkeypatch.setattr(ai_api, "complete", fake_complete)
    monkeypatch.setattr(ai_api, "parse_pick", lambda text, game, size, count: [{"numbers": [1, 2, 3, 4, 5]}])
    a = FastAPI()
    install(a)
    a.include_router(ai_api.router)
    a.include_router(tools.router)
    a.state.pool = FakePool(FakeDB())
    a.state.settings = settings
    a.state.collector = SimpleNamespace(http=None)
    return a


def bearer(role):
    return {"Authorization": f"Bearer {TOK[role]}"}


def cl(app, headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers or {})


PICK = ("POST", "/v1/ai/pick", {"json": {"region": "mb", "count": 1, "size": 5}})
BOARD = ("GET", "/v1/predictions/board", {})
SAVE = ("PUT", "/v1/user/predictions", {"json": {"entries": {}, "lo": {}}})
ENDPOINTS = [PICK, BOARD, SAVE]
IDS = ["ai-pick", "board", "save-predictions"]

# Người không đủ quyền: không đăng nhập, token viewer/editor, phiên quản trị viewer/editor, cookie thành viên.
DENIED = {
    "anonymous": {},
    "bearer-viewer": bearer("viewer"),
    "bearer-editor": bearer("editor"),
    "bearer-bad-token": {"Authorization": "Bearer " + "z" * 32},
    "session-viewer": {"Cookie": "lv_session=viewer", **CSRF},
    "session-editor": {"Cookie": "lv_session=editor", **CSRF},
    "member-cookie": {"Cookie": "lv_user=member", **CSRF},
}


@pytest.mark.parametrize("who", list(DENIED))
@pytest.mark.parametrize("ep", ENDPOINTS, ids=IDS)
async def test_prediction_endpoints_refuse_non_admin(app, ep, who):
    method, url, kw = ep
    async with cl(app, DENIED[who]) as c:
        r = await c.request(method, url, **kw)
    assert r.status_code in (401, 403), (who, url, r.status_code)


@pytest.mark.parametrize("ep", [PICK, BOARD], ids=["ai-pick", "board"])
async def test_prediction_endpoints_admin_bearer_allowed_and_no_store(app, ep):
    # PUT bị loại: Bearer không có user_id nên ghi sổ chỉ kiểm tra qua phiên admin (test dưới)
    method, url, kw = ep
    async with cl(app, bearer("admin")) as c:
        r = await c.request(method, url, **kw)
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")


@pytest.mark.parametrize("ep", ENDPOINTS, ids=IDS)
async def test_prediction_endpoints_admin_session_allowed_and_no_store(app, ep):
    method, url, kw = ep
    async with cl(app, {"Cookie": "lv_session=admin", **CSRF}) as c:
        r = await c.request(method, url, **kw)
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")


async def test_ai_pick_member_does_not_reach_ai_provider(app, monkeypatch):
    called = []

    async def spy(*a, **k):
        called.append(1)
        return "x"

    monkeypatch.setattr(ai_api, "complete", spy)
    async with cl(app, DENIED["member-cookie"]) as c:
        r = await c.post("/v1/ai/pick", json={"region": "mb"})
    assert r.status_code in (401, 403) and called == []


async def test_save_predictions_refused_member_writes_nothing(app):
    async with cl(app, DENIED["member-cookie"]) as c:
        r = await c.put("/v1/user/predictions", json={"entries": {}, "lo": {}})
    assert r.status_code in (401, 403)
    assert not any(s.startswith("INSERT INTO user_prediction_docs") for s in app.state.pool.db.sql)


async def test_board_refused_does_not_query_user_docs(app):
    async with cl(app) as c:
        r = await c.get("/v1/predictions/board")
    assert r.status_code in (401, 403)
    assert not any("user_prediction_docs" in s for s in app.state.pool.db.sql)


async def test_ai_status_stays_public(app):
    async with cl(app) as c:
        r = await c.get("/v1/ai/status")
    assert r.status_code == 200
