"""Luồng SSE: GET /v1/live/stream?region=mb"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..events import CHANNEL
from ..domain.games import ALL_REGIONS
from .errors import ApiError

router = APIRouter(prefix="/v1", tags=["live"])
HEARTBEAT_S = 15


def _frame(event_id: int, topic: str, data: dict) -> str:
    return f"id: {event_id}\nevent: {topic}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/live/stream")
async def stream(request: Request, region: str = "all", last_event_id: int | None = None):
    if region not in ({"all"} | ALL_REGIONS):
        raise ApiError(400, "invalid_param", "region phải là all, mb, mn, mt hoặc vl")
    header_id = request.headers.get("last-event-id")
    since = int(header_id) if header_id and header_id.isdigit() else last_event_id
    pool, redis = request.app.state.pool, request.app.state.redis

    async def gen():
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL.format(region))
        try:
            yield "retry: 3000\n\n"
            sent = since or 0
            if since:  # gửi bù các sự kiện bị lỡ trong 30 phút gần nhất
                async with pool.connection() as conn:
                    rows = await (await conn.execute(
                        """SELECT id, topic, payload FROM outbox_events
                            WHERE id > %s AND published_at IS NOT NULL AND created_at > now() - interval '30 minutes'
                              AND (%s = 'all' OR region_code = %s) ORDER BY id LIMIT 2000""",
                        (since, region, region))).fetchall()
                for r in rows:
                    sent = r["id"]
                    yield _frame(r["id"], r["topic"], r["payload"])
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=HEARTBEAT_S)
                if msg is None:
                    yield ": ping\n\n"
                    continue
                ev = json.loads(msg["data"])
                if ev["id"] <= sent:
                    continue
                sent = ev["id"]
                yield _frame(ev["id"], ev["topic"], ev["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
