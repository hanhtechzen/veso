"""Theo dõi trực tiếp và đối soát: tải từ các nguồn rồi đưa qua quy trình xử lý."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from ..alerts import send
from ..config import VN_TZ, WINDOWS
from ..sources.base import DrawRef, ParseError
from ..sources.registry import active_sources, build
from .context import Ctx
from .fetcher import fetch_raw
from .pipeline import ingest

log = logging.getLogger(__name__)


def to_ref(d: dict) -> DrawRef:
    return DrawRef(d["id"], d["game"], d["region_code"], d["province_code"], d["draw_date"], d["draw_seq"])


async def collect_draws(ctx: Ctx, draws: list[dict]) -> None:
    by_region: dict[str, list[dict]] = {}
    for d in draws:
        by_region.setdefault(d["region_code"], []).append(d)
    for region, items in by_region.items():
        async with ctx.pool.connection() as conn:
            sources = await active_sources(conn, ctx.settings, region)
        for src in sources:
            adapter = build(src, ctx.settings)
            if not adapter:
                continue

            async def one(d: dict, src=src, adapter=adapter):
                ref = to_ref(d)
                fetch_id, res = await fetch_raw(ctx, src, adapter, ref)
                if res is None:
                    return
                try:
                    parsed = adapter.parse(res, ref)
                except ParseError as e:
                    async with ctx.pool.connection() as conn:
                        await conn.execute("UPDATE raw_fetches SET parse_status = 'parse_error', error = %s WHERE id = %s",
                                           (str(e)[:500], fetch_id))
                    ctx.alerts.append(("warn", f"Nguồn {src['code']}: không nhận ra cấu trúc dữ liệu ({e})."))
                    return
                async with ctx.pool.connection() as conn:
                    out = await ingest(conn, ctx.settings, ref.id, src["code"], parsed.prizes, fetch_id=fetch_id,
                                       prize_map=adapter.prize_map, source_complete=parsed.complete)
                    seq = (parsed.meta or {}).get("draw_seq")
                    if seq:
                        await conn.execute("UPDATE lottery_draws SET draw_seq = %s WHERE id = %s",  # số kỳ của nguồn chính thức ghi đè số kỳ tự đoán
                                           (seq, ref.id))
                ctx.alerts.extend(out["alerts"])

            for d, r in zip(items, await asyncio.gather(*(one(d) for d in items), return_exceptions=True)):
                if isinstance(r, Exception):  # một kỳ lỗi không làm bỏ dở các kỳ khác
                    log.error("Lỗi khi tải %s: %r", repr(d)[:120], r)
    await flush_alerts(ctx)


async def flush_alerts(ctx: Ctx) -> None:
    pending, ctx.alerts = ctx.alerts, []
    for level, text in pending:
        await send(ctx.settings, ctx.http, text, level)


async def pending_draws(ctx: Ctx, *, region: str | None = None, day: date | None = None,
                        since: date | None = None, include_published: bool = False,
                        draw_ids: list[str] | None = None) -> list[dict]:
    q = ["SELECT * FROM lottery_draws WHERE scheduled_at <= now() + interval '10 minutes'"]
    args: list = []
    if not include_published:
        q.append("AND current_version IS NULL")
    if region:
        q.append("AND region_code = %s"); args.append(region)
    if day:
        q.append("AND draw_date = %s"); args.append(day)
    if since:
        q.append("AND draw_date >= %s"); args.append(since)
    if draw_ids:
        q.append("AND id = ANY(%s)"); args.append(draw_ids)
    q.append("ORDER BY scheduled_at")
    async with ctx.pool.connection() as conn:
        cur = await conn.execute(" ".join(q), args)
        return await cur.fetchall()


async def watch(ctx: Ctx, region: str, day: date) -> None:
    """Phiên theo dõi trực tiếp: tải liên tục trong khung giờ, dừng sớm khi mọi kỳ đã công bố."""
    w = WINDOWS[region]
    end = datetime.combine(day, w.live_end, VN_TZ)
    log.info("Bắt đầu theo dõi %s ngày %s đến %s", region, day, end.time())
    while datetime.now(VN_TZ) < end:
        try:
            draws = await pending_draws(ctx, region=region, day=day)
            if not draws:
                log.info("Mọi kỳ %s ngày %s đã công bố, dừng theo dõi", region, day)
                return
            await collect_draws(ctx, draws)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi trong phiên theo dõi %s", region)
        await asyncio.sleep(w.poll_seconds)
    log.info("Hết khung theo dõi %s ngày %s", region, day)
