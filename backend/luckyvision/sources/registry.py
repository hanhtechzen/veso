"""Tạo bộ chuyển đổi từ cấu hình trong bảng data_sources."""
from __future__ import annotations

from ..config import Settings
from .base import Adapter
from .fixture import FixtureAdapter
from .http_json import HttpJsonAdapter
from .minhngoc import MinhNgocAdapter
from .vietlott import VietlottPower655Adapter
from .xosocomvn import XosoComVnAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    "fixture": FixtureAdapter,
    "http_json": HttpJsonAdapter,
    "minhngoc": MinhNgocAdapter,
    "xosocomvn": XosoComVnAdapter,
    "vietlott_655": VietlottPower655Adapter,
}


def build(row: dict, settings: Settings) -> Adapter | None:
    cls = ADAPTERS.get(row["adapter"])
    return cls(row["code"], row.get("config") or {}, settings) if cls else None


async def active_sources(conn, settings: Settings, region: str) -> list[dict]:
    """Nguồn được phép chạy cho một miền: đã bật, đã duyệt pháp lý, đúng miền.

    Nguồn 'fixture' chỉ chạy khi APP_ENV=dev.
    """
    cur = await conn.execute(
        """SELECT * FROM data_sources
            WHERE enabled AND legal_approved AND adapter <> 'manual'
              AND (cardinality(regions) = 0 OR %s = ANY(regions))
              AND (kind <> 'fixture' OR %s)
            ORDER BY priority, code""",
        (region, settings.is_dev),
    )
    return await cur.fetchall()
