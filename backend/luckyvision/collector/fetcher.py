"""Bước 1: tải từ nguồn, lưu bản gốc nén vào /data/raw, ghi raw_fetches."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import logging
import random
from datetime import datetime
from pathlib import Path

import httpx

from ..config import VN_TZ
from ..sources.base import Adapter, DrawRef, FetchResult
from .context import Ctx

log = logging.getLogger(__name__)
RETRIES = 3


async def _fetch_with_retry(ctx: Ctx, adapter: Adapter, draw: DrawRef, rate_ms: int) -> FetchResult:
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        await ctx.gate.wait_turn(adapter.code, rate_ms)
        try:
            res = await adapter.fetch(ctx.http, draw)
            if res.status >= 500:
                raise httpx.HTTPError(f"HTTP {res.status}")
            return res
        except (httpx.HTTPError, OSError) as e:
            last_exc = e
            if attempt < RETRIES - 1:
                await asyncio.sleep(min(60.0, delay) + random.uniform(0, 1))
                delay *= 2
    assert last_exc is not None
    raise last_exc


def _store(raw_dir: str, draw: DrawRef, source: str, body: bytes) -> str:
    now = datetime.now(VN_TZ)
    folder = Path(raw_dir) / f"{draw.draw_date:%Y/%m/%d}" / draw.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source}-{now:%H%M%S%f}.gz"
    with gzip.open(path, "wb") as f:
        f.write(body)
    return str(path)


async def fetch_raw(ctx: Ctx, src: dict, adapter: Adapter, draw: DrawRef) -> tuple[int | None, FetchResult | None]:
    """Trả về (fetch_id, kết quả tải). (None, None) nếu nguồn chưa có dữ liệu mới hoặc lỗi."""
    code = src["code"]
    if ctx.gate.is_open(code):
        return None, None
    try:
        res = await _fetch_with_retry(ctx, adapter, draw, src["rate_limit_ms"])
    except Exception as e:  # noqa: BLE001
        tripped = ctx.gate.failure(code)
        async with ctx.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO raw_fetches (source_code, draw_id, parse_status, error) VALUES (%s, %s, 'fetch_error', %s)",
                (code, draw.id, str(e)[:500]))
        if tripped:
            ctx.alerts.append(("warn", f"Nguồn {code} lỗi 5 lần liên tiếp, tạm ngắt 10 phút."))
        return None, None
    ctx.gate.success(code)
    if res.status == 404 or not res.body:
        return None, None  # nguồn chưa có kết quả kỳ này
    digest = hashlib.sha256(res.body).hexdigest()
    async with ctx.pool.connection() as conn:
        cur = await conn.execute(
            """SELECT sha256 FROM raw_fetches WHERE draw_id = %s AND source_code = %s AND sha256 IS NOT NULL
                ORDER BY id DESC LIMIT 1""", (draw.id, code))
        prev = await cur.fetchone()
        if prev and prev["sha256"] == digest:
            return None, None  # không đổi so với lần trước
        path = await asyncio.to_thread(_store, ctx.settings.raw_dir, draw, code, res.body)
        cur = await conn.execute(
            """INSERT INTO raw_fetches (source_code, draw_id, url, http_status, sha256, file_path)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (code, draw.id, res.url, res.status, digest, path))
        row = await cur.fetchone()
    return row["id"], res
