"""Kết nối PostgreSQL và áp dụng migration."""
from __future__ import annotations

import logging
from datetime import date
from importlib import resources

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .domain.games import game_of_region
from .domain.prizes import DEFAULT_STRUCTURES, PrizeSpec, Structure

log = logging.getLogger(__name__)


def make_pool(url: str, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    return AsyncConnectionPool(url, min_size=min_size, max_size=max_size, open=False,
                               kwargs={"row_factory": dict_row})


def migrate(url: str) -> list[str]:
    """Áp dụng lần lượt các tệp migrations/*.sql chưa chạy. Trả về tên các tệp vừa áp dụng."""
    applied: list[str] = []
    files = sorted(p for p in resources.files("luckyvision.migrations").iterdir() if p.name.endswith(".sql"))
    with psycopg.connect(url) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("SELECT pg_advisory_lock(424242)")
        try:
            done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
            for f in files:
                if f.name in done:
                    continue
                log.info("Áp dụng migration %s", f.name)
                with conn.transaction():
                    conn.execute(f.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
                applied.append(f.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(424242)")
    return applied


async def load_structure(conn, region: str, day: date) -> Structure:
    cur = await conn.execute(
        """SELECT DISTINCT ON (prize_code) prize_code, name, sort_order, count, digits
             FROM prize_structures
            WHERE region_code = %s AND valid_from <= %s
            ORDER BY prize_code, valid_from DESC""",
        (region, day),
    )
    rows = await cur.fetchall()
    if not rows:
        return DEFAULT_STRUCTURES[region]
    game = game_of_region(region)
    specs = tuple(sorted((PrizeSpec(r["prize_code"], r["name"], r["count"], r["digits"], r["sort_order"]) for r in rows),
                         key=lambda p: p.sort_order))
    return Structure(region, game, specs)
