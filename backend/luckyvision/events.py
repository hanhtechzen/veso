"""Sự kiện realtime theo mẫu outbox: ghi cùng giao dịch, rồi chuyển sang Redis."""
from __future__ import annotations

import asyncio
import json
import logging

from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)
CHANNEL = "lv:events:{}"


async def emit(conn, topic: str, region: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO outbox_events (topic, region_code, payload) VALUES (%s, %s, %s)",
        (topic, region, Jsonb(payload)),
    )


async def relay_once(pool, redis, batch: int = 200) -> int:
    """Gửi các sự kiện chưa gửi sang Redis. Trả về số sự kiện đã gửi."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT id, topic, region_code, payload FROM outbox_events
                WHERE published_at IS NULL ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",
            (batch,),
        )
        rows = await cur.fetchall()
        for r in rows:
            msg = json.dumps({"id": r["id"], "topic": r["topic"], "region": r["region_code"], "data": r["payload"]},
                             ensure_ascii=False)
            await redis.publish(CHANNEL.format(r["region_code"] or "all"), msg)
            await redis.publish(CHANNEL.format("all"), msg)
        if rows:
            await conn.execute("UPDATE outbox_events SET published_at = now() WHERE id = ANY(%s)",
                               ([r["id"] for r in rows],))
        return len(rows)


async def relay_loop(pool, redis, stop: asyncio.Event, idle_s: float = 0.5) -> None:
    while not stop.is_set():
        try:
            n = await relay_once(pool, redis)
        except Exception:  # noqa: BLE001 - không để vòng lặp chết vì một lỗi tạm thời
            log.exception("Lỗi khi chuyển sự kiện sang Redis")
            n = 0
        if n == 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=idle_s)
            except asyncio.TimeoutError:
                pass
