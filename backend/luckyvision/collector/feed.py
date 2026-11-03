"""Lấy kết quả theo dòng mới nhất cho các trò chơi không lập lịch trước (Keno, Bingo18, Lotto 5/35, Max 3D...).

Mỗi lần chạy: đọc trang đầu của nguồn, tạo kỳ quay nếu chưa có, đưa kết quả qua đúng quy trình
kiểm tra, đối chiếu, công bố như các loại khác. Dừng đọc trang sau khi gặp toàn kỳ đã có.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, time

from ..config import VN_TZ
from ..domain.games import GAMES
from ..sources.registry import build
from .live import flush_alerts
from .pipeline import ingest
from .planner import make_draw_id, make_seq_draw_id

log = logging.getLogger(__name__)
# Khoảng cách tối thiểu giữa hai lần đọc của mỗi trò chơi (giây)
MIN_INTERVAL = {"keno": 300, "bingo18": 300, "lotto535": 900, "max3d": 1800, "max3dpro": 1800}
_LAST: dict[str, float] = {}


def draw_id_for(game, day, seq) -> str:
    return make_seq_draw_id(game.region, game.code, day, seq, game.seq_width) if game.multi_daily else make_draw_id(game.region, game.code, day)


async def feed_sources(ctx, game_code: str | None = None) -> list[dict]:
    async with ctx.pool.connection() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM data_sources WHERE adapter = 'vietlott_feed' AND enabled AND legal_approved ORDER BY priority")).fetchall()
    return [r for r in rows if not game_code or (r["config"] or {}).get("game") == game_code]


async def ingest_rows(ctx, src: dict, rows) -> tuple[int, int]:
    """Trả về (số kỳ mới, số kỳ đã có)."""
    game = GAMES[src["config"]["game"]]
    new = known = 0
    for row in sorted(rows, key=lambda r: (r.day, r.seq)):
        did = draw_id_for(game, row.day, row.seq)
        async with ctx.pool.connection() as conn:
            ex = await (await conn.execute("SELECT current_version FROM lottery_draws WHERE id = %s", (did,))).fetchone()
            if ex and ex["current_version"]:
                known += 1
                continue
            at = datetime.combine(row.day, time(18, 0) if not game.multi_daily else time(0, 0), VN_TZ)
            await conn.execute(
                """INSERT INTO lottery_draws (id, game, region_code, province_code, draw_date, draw_seq, scheduled_at, warn_at, critical_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL) ON CONFLICT (id) DO NOTHING""",
                (did, game.code, game.region, game.code, row.day, row.seq, at))
            out = await ingest(conn, ctx.settings, did, src["code"], row.prizes, source_complete=True)
            ctx.alerts.extend(out["alerts"])
            new += 1
    return new, known


async def run_feed(ctx, game_code: str | None = None, pages: int = 1, force: bool = False) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for src in await feed_sources(ctx, game_code):
        code = src["config"]["game"]
        now = _time.monotonic()
        if not force and now - _LAST.get(code, 0) < MIN_INTERVAL.get(code, 900):
            continue
        _LAST[code] = now
        adapter = build(src, ctx.settings)
        total_new = total_known = 0
        for page in range(pages):
            try:
                _res, rows = await adapter.fetch_page(ctx.http, page)
            except Exception as e:  # noqa: BLE001
                log.warning("Nguồn %s lỗi: %s", src["code"], e)
                ctx.alerts.append(("warn", f"Nguồn {src['code']} lỗi khi đọc kết quả: {e}"))
                break
            if not rows:
                break
            n, k = await ingest_rows(ctx, src, rows)
            total_new += n
            total_known += k
            if n == 0 and pages > 1 and k:  # đã gặp toàn kỳ cũ
                break
            await asyncio.sleep(src["rate_limit_ms"] / 1000)
        result[code] = (total_new, total_known)
    await flush_alerts(ctx)
    return result


def in_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now(VN_TZ)
    return time(6, 0) <= now.time() <= time(23, 30)
