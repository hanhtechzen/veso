"""Quản trị: công bố/sửa kết quả (verify, put_results, publish, ingest) và POST /admin/collect.

Không dùng Postgres thật: FakeDB giả lập vừa đủ các câu SQL mà pipeline/admin gọi, theo từ khóa trong câu SQL.
Giả định về SQL (để mã mới còn chạy được với FakeDB):
- Checksum của phiên bản đang công bố lấy qua câu SELECT có JOIN draw_versions (như try_verify hiện tại).
- Nếu ingest dùng ON CONFLICT ... DO UPDATE ... RETURNING id, hoặc SELECT id FROM result_candidates
  WHERE draw_id=%s AND source_code=%s AND checksum=%s (tham số theo thứ tự đó) thì FakeDB đều trả đúng id cũ.

Giao diện kỳ vọng ở mã:
- pipeline.publish(...) ném ValueError khi checksum của ứng viên trùng phiên bản đang công bố;
  admin.verify đổi thành ApiError(409, "already_published").
- Lý do (reason) được strip, phải dài >= 3 ký tự, sai thì ApiError(400, "invalid_param") (khi kỳ đã có current_version).
- POST /admin/collect giữ task trong app.state.collect_tasks: dict[draw_id, asyncio.Task] (tạo lười nếu chưa có),
  trùng draw_id đang chạy -> ApiError(409, "collect_in_progress"); task xong thì bị gỡ khỏi dict;
  lỗi trong task được ghi log mức ERROR qua add_done_callback.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from luckyvision.api import admin
from luckyvision.api.errors import install
from luckyvision.collector import pipeline
from luckyvision.config import VN_TZ, Settings
from luckyvision.domain.prizes import DEFAULT_STRUCTURES, checksum

FX = Path(__file__).resolve().parents[1] / "fixtures"
DRAW_ID = "mn-tp-hcm-2026-10-26"
PRIZES = json.loads((FX / f"{DRAW_ID}.json").read_text(encoding="utf-8"))["prizes"]
TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 10, 26, 17, 0, tzinfo=VN_TZ)


class Cur:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows if rows is not None else ([] if row is None else [row])

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


class FakeDB:
    def __init__(self, current_version=None, published_checksum=None, status="collected"):
        self.draw = {"id": DRAW_ID, "game": "xs", "region_code": "mn", "province_code": "tp-hcm",
                     "draw_date": NOW.date(), "status": status, "current_version": current_version,
                     "updated_at": NOW}
        self.published_checksum = published_checksum
        self.cands: dict[int, dict] = {}
        self.keys: dict[tuple, int] = {}
        self.versions: list = []
        self.events: list[str] = []
        self.sql: list[str] = []
        self.add_candidate(1, PRIZES)  # ứng viên số 1: bản mn đầy đủ, hợp lệ

    def add_candidate(self, cid, payload, source="srcA"):
        self.cands[cid] = {"id": cid, "payload": payload, "is_complete": True, "checksum": checksum(payload)}
        self.keys[(DRAW_ID, source, checksum(payload))] = cid

    # ---- giao diện psycopg ----
    async def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.sql.append(s)
        params = params or ()
        if s.startswith("SELECT * FROM lottery_draws"):
            return Cur(dict(self.draw))
        if "FROM draw_versions" in s and "JOIN" in s:
            return Cur({"checksum": self.published_checksum} if self.published_checksum else None)
        if "max(version)" in s:
            return Cur({"v": (self.draw["current_version"] or 0) + 1 + 0})
        if s.startswith("INSERT INTO draw_versions"):
            self.versions.append(params)
            return Cur()
        if s.startswith("INSERT INTO outbox_events"):
            self.events.append(params[0])
            return Cur()
        if s.startswith("INSERT INTO result_candidates"):
            key = (params[0], params[1], params[5])
            if key in self.keys:
                return Cur({"id": self.keys[key]}) if "DO UPDATE" in s else Cur(None)
            cid = max(self.cands, default=0) + 1
            self.cands[cid] = {"id": cid, "payload": params[3].obj, "is_complete": params[4], "checksum": params[5]}
            self.keys[key] = cid
            return Cur({"id": cid})
        if s.startswith("SELECT") and "result_candidates" in s:
            if "<> 'manual'" in s:
                return Cur(rows=[])
            if len(params) == 3 and params[1] == "manual":
                cid = self.keys.get(tuple(params))
                return Cur({"id": cid} if cid else None)
            return Cur(self.cands.get(params[0]))
        return Cur()

    def cursor(self):
        db = self

        class C:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            async def executemany(self_, sql, rows):
                return None

        return C()


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


def make_app(monkeypatch, **db_kw):
    db = FakeDB(**db_kw)

    async def load_structure(conn, region, day):
        return DEFAULT_STRUCTURES["mn"]

    monkeypatch.setattr(admin, "load_structure", load_structure)
    monkeypatch.setattr(pipeline, "load_structure", load_structure)
    settings = Settings(_env_file=None, admin_tokens=f"{TOKEN}:admin:tester")
    monkeypatch.setattr(admin, "get_settings", lambda: settings)
    app = FastAPI()
    install(app)
    app.include_router(admin.router)
    app.state.pool = FakePool(db)
    app.state.settings = settings
    app.state.collector = object()
    return app, db


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=AUTH)


async def verify(app, reason, cid=1):
    async with client(app) as cl:
        return await cl.post(f"/v1/admin/draws/{DRAW_ID}/verify", json={"candidate_id": cid, "reason": reason})


async def put(app, reason, prizes=None):
    async with client(app) as cl:
        return await cl.put(f"/v1/admin/draws/{DRAW_ID}/results", json={"prizes": prizes or PRIZES, "reason": reason})


def code_of(r):
    return r.json()["error"]["code"]


# ===================== Mục 2: không công bố lại bản trùng phiên bản hiện hành =====================
async def test_verify_rejects_candidate_identical_to_current_version(monkeypatch):
    app, db = make_app(monkeypatch, current_version=1, published_checksum=checksum(PRIZES))
    r = await verify(app, "kiểm tra lại")
    assert r.status_code == 409 and code_of(r) == "already_published"
    assert db.versions == []
    assert "draw.corrected" not in db.events


async def test_publish_rejects_candidate_identical_to_current_version(monkeypatch):
    app, db = make_app(monkeypatch, current_version=1, published_checksum=checksum(PRIZES))
    with pytest.raises(ValueError):
        await pipeline.publish(db, DRAW_ID, 1, "user:x", "kiểm tra lại")
    assert db.versions == []
    assert "draw.corrected" not in db.events


async def test_publish_different_candidate_creates_new_version_and_corrected_event(monkeypatch):
    app, db = make_app(monkeypatch, current_version=1, published_checksum="khac-hoan-toan")
    v = await pipeline.publish(db, DRAW_ID, 1, "user:x", "sửa số giải nhất")
    assert v == 2 and len(db.versions) == 1
    assert db.events == ["draw.corrected"]


async def test_first_publish_creates_version_1(monkeypatch):
    app, db = make_app(monkeypatch)
    assert await pipeline.publish(db, DRAW_ID, 1, "user:x", None) == 1
    assert db.events == ["draw.published"]


# ===================== Mục 3: kiểm tra lý do =====================
BAD_REASONS = [None, "", "  ", "ab", " ab "]


@pytest.mark.parametrize("reason", BAD_REASONS)
async def test_verify_published_draw_requires_valid_reason(monkeypatch, reason):
    app, db = make_app(monkeypatch, current_version=1, published_checksum="khac")
    r = await verify(app, reason)
    assert r.status_code == 400 and code_of(r) == "invalid_param"
    assert db.versions == []


@pytest.mark.parametrize("reason", BAD_REASONS)
async def test_put_results_published_draw_requires_valid_reason(monkeypatch, reason):
    app, db = make_app(monkeypatch, current_version=1, published_checksum="khac")
    r = await put(app, reason)
    assert r.status_code == 400 and code_of(r) == "invalid_param"
    assert not any(s.startswith("INSERT INTO result_candidates") for s in db.sql)


@pytest.mark.parametrize("reason", ["abc", "  abc  ", "sửa số"])
async def test_verify_accepts_reason_of_three_chars_after_strip(monkeypatch, reason):
    app, db = make_app(monkeypatch, current_version=1, published_checksum="khac")
    r = await verify(app, reason)
    assert r.status_code == 200 and r.json()["version"] == 2


@pytest.mark.parametrize("reason", ["abc", "  abc  "])
async def test_put_results_accepts_reason_of_three_chars_after_strip(monkeypatch, reason):
    app, db = make_app(monkeypatch, current_version=1, published_checksum="khac")
    r = await put(app, reason)
    assert r.status_code == 200 and r.json()["candidate_id"] is not None


async def test_first_publish_does_not_need_reason(monkeypatch):
    app, db = make_app(monkeypatch)
    r = await verify(app, None)
    assert r.status_code == 200 and r.json()["version"] == 1


# ===================== Mục 4: nhập tay trùng nội dung trả cùng candidate_id =====================
async def test_put_results_identical_payload_twice_returns_same_candidate_id(monkeypatch):
    app, db = make_app(monkeypatch)
    r1 = await put(app, None)
    r2 = await put(app, None)
    assert r1.status_code == 200 and r2.status_code == 200
    id1, id2 = r1.json()["candidate_id"], r2.json()["candidate_id"]
    assert id1 is not None
    assert id2 == id1


async def test_ingest_manual_duplicate_returns_existing_candidate_id(monkeypatch):
    app, db = make_app(monkeypatch)
    settings = app.state.settings
    a = await pipeline.ingest(db, settings, DRAW_ID, "manual", PRIZES, created_by="user:x")
    b = await pipeline.ingest(db, settings, DRAW_ID, "manual", PRIZES, created_by="user:x")
    assert a["candidate_id"] is not None
    assert b["candidate_id"] == a["candidate_id"]


# ===================== Mục 5: POST /admin/collect =====================
async def _spin():
    for _ in range(10):
        await asyncio.sleep(0)


def patch_collect(monkeypatch, fake_collect):
    async def fake_pending(ctx, **kw):
        return [{"id": i, "region_code": "mn"} for i in kw["draw_ids"]]

    monkeypatch.setattr(admin, "pending_draws", fake_pending)
    monkeypatch.setattr(admin, "collect_draws", fake_collect)


async def post_collect(app, draw_id=DRAW_ID):
    async with client(app) as cl:
        return await cl.post("/v1/admin/collect", json={"draw_id": draw_id})


async def test_collect_keeps_task_referenced_in_app_state(monkeypatch):
    app, _ = make_app(monkeypatch)
    release = asyncio.Event()

    async def blocking(ctx, draws):
        await release.wait()

    patch_collect(monkeypatch, blocking)
    r = await post_collect(app)
    assert r.status_code == 202
    await _spin()
    task = app.state.collect_tasks[DRAW_ID]
    assert isinstance(task, asyncio.Task) and not task.done()
    release.set()
    await asyncio.wait_for(task, 2)
    await _spin()
    assert DRAW_ID not in app.state.collect_tasks  # task xong thì được gỡ


async def test_collect_same_draw_while_running_is_rejected_with_409(monkeypatch):
    app, _ = make_app(monkeypatch)
    release = asyncio.Event()
    calls = []

    async def blocking(ctx, draws):
        calls.append([d["id"] for d in draws])
        await release.wait()

    patch_collect(monkeypatch, blocking)
    assert (await post_collect(app)).status_code == 202
    await _spin()
    r2 = await post_collect(app)
    assert r2.status_code == 409 and code_of(r2) == "collect_in_progress"
    other = await post_collect(app, "mn-tp-hcm-2026-10-27")  # kỳ khác vẫn nhận
    assert other.status_code == 202
    await _spin()
    assert calls == [[DRAW_ID], ["mn-tp-hcm-2026-10-27"]]
    tasks = list(app.state.collect_tasks.values())
    release.set()
    await asyncio.wait_for(asyncio.gather(*tasks), 2)
    await _spin()
    r3 = await post_collect(app)  # chạy xong thì nhận lại được
    assert r3.status_code == 202
    await _spin()


async def test_collect_task_exception_is_logged(monkeypatch, caplog):
    app, _ = make_app(monkeypatch)
    release = asyncio.Event()

    async def failing(ctx, draws):
        await release.wait()
        raise RuntimeError("boom-collect")

    patch_collect(monkeypatch, failing)
    caplog.set_level(logging.ERROR)
    assert (await post_collect(app)).status_code == 202
    await _spin()
    task = app.state.collect_tasks[DRAW_ID]
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    await _spin()
    assert any("boom-collect" in r.getMessage() or (r.exc_info and "boom-collect" in str(r.exc_info[1]))
               for r in caplog.records if r.levelno >= logging.ERROR)
