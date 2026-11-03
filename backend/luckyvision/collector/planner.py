"""Lập danh sách kỳ quay dự kiến của một ngày (mục 3 tài liệu thiết kế)."""
from __future__ import annotations

import re

from datetime import date, datetime

from ..domain.games import GAMES
from ..config import VN_TZ, WINDOWS


def make_draw_id(region: str, province: str, day: date) -> str:
    return f"{region}-{province}-{day.isoformat()}"


DRAW_ID_RE = re.compile(r"^(?P<region>[a-z0-9]+)-(?P<province>[a-z0-9-]+?)-(?P<day>\d{4}-\d{2}-\d{2})(?:-(?P<seq>\d+))?$")


def parse_draw_id(draw_id: str) -> tuple[str, str, date]:
    """'mn-tp-hcm-2026-10-26' -> ('mn', 'tp-hcm', date(2026, 10, 26)).
    Trò chơi quay nhiều kỳ mỗi ngày có thêm số kỳ ở cuối: 'keno-keno-2026-11-03-0301574'."""
    m = DRAW_ID_RE.match(draw_id or "")
    if not m:
        raise ValueError(draw_id)
    return m["region"], m["province"], date.fromisoformat(m["day"])


def make_seq_draw_id(region: str, province: str, day: date, seq: int, width: int = 5) -> str:
    return f"{region}-{province}-{day.isoformat()}-{seq:0{width}d}"


async def plan_day(conn, day: date) -> int:
    cur = await conn.execute(
        """SELECT s.province_code, s.draw_time, p.region_code, p.game
             FROM draw_schedules s JOIN provinces p ON p.code = s.province_code
            WHERE p.active AND s.iso_weekday = %s AND s.valid_from <= %s
              AND (s.valid_to IS NULL OR s.valid_to >= %s)
              AND NOT EXISTS (SELECT 1 FROM draw_holidays h
                               WHERE h.region_code = p.region_code AND %s BETWEEN h.date_from AND h.date_to)""",
        (day.isoweekday(), day, day, day))
    created = 0
    for r in await cur.fetchall():
        region = r["region_code"]
        w = WINDOWS.get(region)
        seq = None
        if r["game"] in GAMES:
            c2 = await conn.execute(
                "SELECT max(draw_seq) AS s FROM lottery_draws WHERE province_code = %s AND draw_date < %s",
                (r["province_code"], day))
            last = (await c2.fetchone())["s"]
            seq = last + 1 if last else None
        res = await conn.execute(
            """INSERT INTO lottery_draws (id, game, region_code, province_code, draw_date, draw_seq,
                                          scheduled_at, warn_at, critical_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (make_draw_id(region, r["province_code"], day), r["game"], region, r["province_code"], day, seq,
             datetime.combine(day, r["draw_time"], VN_TZ),
             datetime.combine(day, w.warn, VN_TZ) if w else None,
             datetime.combine(day, w.critical, VN_TZ) if w else None))
        created += res.rowcount
    return created
