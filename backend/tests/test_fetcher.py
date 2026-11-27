"""Bộ tải (collector/fetcher.py): phân loại lỗi tạm thời / lỗi vĩnh viễn / 404, Retry-After, cổng ngắt mạch.

Không gọi mạng, không dùng Postgres: adapter giả, ctx.pool giả, asyncio.sleep bị thay.

Giao diện test kỳ vọng:
- FetchResult có thêm trường tùy chọn `headers: dict[str, str]` (mặc định rỗng); fetcher đọc "Retry-After"
  (không phân biệt hoa thường, số giây) và ngủ ít nhất chừng đó giây trước lần thử kế tiếp.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from xs247.collector import fetcher
from xs247.sources.base import DrawRef, FetchResult

DRAW = DrawRef("mb-mb-2026-11-02", "xs", "mb", "mb", date(2026, 11, 2))
SRC = {"code": "srcA", "rate_limit_ms": 0}


class FakeGate:
    def __init__(self):
        self.successes = 0
        self.failures = 0

    def is_open(self, code):
        return False

    async def wait_turn(self, code, rate_ms):
        return None

    def success(self, code):
        self.successes += 1

    def failure(self, code):
        self.failures += 1
        return False


class FakeCursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return [] if self.row is None else [self.row]


class FakeConn:
    def __init__(self, log):
        self.log = log

    async def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))
        if "RETURNING id" in sql:
            return FakeCursor({"id": 42})
        return FakeCursor(None)  # SELECT sha256: chưa có bản trước


class FakePool:
    def __init__(self):
        self.log: list = []

    def connection(self):
        log = self.log

        class CM:
            async def __aenter__(self_):
                return FakeConn(log)

            async def __aexit__(self_, *a):
                return False

        return CM()


class ScriptedAdapter:
    code = "srcA"

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def fetch(self, http, draw):
        self.calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def res(status, body=b"<html>ok</html>", **kw):
    return FetchResult("http://x/y", status, body, **kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(fetcher.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(fetcher.random, "uniform", lambda a, b: 0.0)
    ctx = SimpleNamespace(gate=FakeGate(), pool=FakePool(), http=None, alerts=[],
                          settings=SimpleNamespace(raw_dir=str(tmp_path)))
    return ctx, sleeps


def fetch_error_rows(ctx):
    return [(s, p) for s, p in ctx.pool.log if "INSERT INTO raw_fetches" in s and "fetch_error" in s]


def ok_rows(ctx):
    return [(s, p) for s, p in ctx.pool.log if "INSERT INTO raw_fetches" in s and "RETURNING id" in s]


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_transient_status_is_retried_then_succeeds(env, status):
    ctx, sleeps = env
    adapter = ScriptedAdapter([res(status, b""), res(200)])
    fid, r = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert adapter.calls == 2
    assert fid == 42 and r.status == 200
    assert len(sleeps) == 1
    assert ctx.gate.failures == 0 and ctx.gate.successes == 1
    assert fetch_error_rows(ctx) == []


async def test_429_every_attempt_is_a_fetch_error_not_a_success(env):
    ctx, _ = env
    adapter = ScriptedAdapter([res(429, b"slow down")])
    out = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert out == (None, None)
    assert adapter.calls == fetcher.RETRIES
    assert ctx.gate.failures == 1
    assert ctx.gate.successes == 0
    assert len(fetch_error_rows(ctx)) == 1
    assert ok_rows(ctx) == []


async def test_persistent_5xx_is_a_fetch_error(env):
    ctx, _ = env
    adapter = ScriptedAdapter([res(503, b"")])
    out = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert out == (None, None)
    assert ctx.gate.failures == 1 and ctx.gate.successes == 0
    assert len(fetch_error_rows(ctx)) == 1


async def test_retry_after_header_is_respected_on_429(env):
    ctx, sleeps = env
    adapter = ScriptedAdapter([res(429, b"", headers={"Retry-After": "30"}), res(200)])
    fid, _ = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert fid == 42
    assert sleeps and sleeps[0] >= 30  # mặc định chỉ chờ ~2 giây


async def test_retry_after_header_is_respected_on_503(env):
    ctx, sleeps = env
    adapter = ScriptedAdapter([res(503, b"", headers={"Retry-After": "12"}), res(200)])
    await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert sleeps and sleeps[0] >= 12


@pytest.mark.parametrize("status", [403, 410, 401, 400])
async def test_other_4xx_is_an_error_not_a_success(env, status):
    ctx, _ = env
    adapter = ScriptedAdapter([res(status, b"<html>forbidden</html>")])
    out = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert out == (None, None)
    assert ctx.gate.failures == 1
    assert ctx.gate.successes == 0          # không được xóa bộ đếm lỗi
    assert adapter.calls == 1               # lỗi 4xx không phải lỗi tạm thời, không thử lại
    rows = fetch_error_rows(ctx)
    assert len(rows) == 1 and str(status) in str(rows[0][1])
    assert ok_rows(ctx) == []               # không lưu bản gốc, không để đem đi phân tích


async def test_404_keeps_current_behavior_source_has_no_result_yet(env):
    ctx, sleeps = env
    adapter = ScriptedAdapter([res(404, b"not found")])
    out = await fetcher.fetch_raw(ctx, SRC, adapter, DRAW)
    assert out == (None, None)
    assert adapter.calls == 1 and sleeps == []
    assert ctx.gate.successes == 1 and ctx.gate.failures == 0
    assert ctx.pool.log == []               # không ghi gì


async def test_empty_body_keeps_current_behavior(env):
    ctx, _ = env
    out = await fetcher.fetch_raw(ctx, SRC, ScriptedAdapter([res(200, b"")]), DRAW)
    assert out == (None, None)
    assert ctx.gate.successes == 1 and ctx.gate.failures == 0
    assert ctx.pool.log == []


async def test_200_is_stored_and_marks_success(env):
    ctx, _ = env
    fid, r = await fetcher.fetch_raw(ctx, SRC, ScriptedAdapter([res(200)]), DRAW)
    assert fid == 42 and r.status == 200
    assert ctx.gate.successes == 1 and ctx.gate.failures == 0
    assert len(ok_rows(ctx)) == 1
