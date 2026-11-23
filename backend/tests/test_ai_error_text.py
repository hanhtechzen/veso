"""Lỗi từ nhà cung cấp AI không được lọt nguyên văn ra người dùng: chỉ ghi nhật ký, trả câu thân thiện."""
from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from luckyvision import ai as ai_mod
from luckyvision.api import ai as ai_api
from luckyvision.api.errors import install
from luckyvision.config import Settings

SECRET = "SECRET-PROVIDER-BODY quota exceeded for key sk-abc123"
FRIENDLY = "Trợ lý AI đang bận, thử lại sau ít phút."


class FakeHttp:
    async def post(self, url, **kw):
        return httpx.Response(500, text=SECRET, request=httpx.Request("POST", url))


class Pool:
    def connection(self):
        class CM:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return False

        return CM()


@pytest.fixture
def app(monkeypatch):
    settings = Settings(_env_file=None, ai_api_key="k", ai_requests_per_minute=10_000)

    async def fake_ctx(conn, region, province):
        return {"hot_last_30": [], "longest_gaps": [], "draws_analyzed": 0}

    monkeypatch.setattr(ai_api, "stats_context", fake_ctx)
    a = FastAPI()
    install(a)
    a.include_router(ai_api.router)
    a.state.pool = Pool()
    a.state.settings = settings
    a.state.collector = SimpleNamespace(http=FakeHttp())
    return a


async def test_complete_hides_provider_body_and_logs_it(caplog):
    settings = Settings(_env_file=None, ai_api_key="k")
    with caplog.at_level(logging.WARNING, logger="luckyvision.ai"):
        with pytest.raises(ai_mod.AiError) as ei:
            await ai_mod.complete(settings, FakeHttp(), "s", "u")
    assert str(ei.value) == FRIENDLY and "SECRET" not in str(ei.value)
    assert "SECRET-PROVIDER-BODY" in caplog.text and "500" in caplog.text


async def test_ask_endpoint_returns_friendly_error(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/ai/ask", json={"question": "Số nào hay về?", "region": "mb"})
    assert r.status_code == 502
    assert "SECRET" not in r.text and "sk-abc123" not in r.text
    err = r.json()["error"]
    assert err["code"] == "ai_error" and err["message"] == FRIENDLY
