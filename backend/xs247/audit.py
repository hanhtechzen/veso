"""Nhật ký quản trị (chỉ thêm, không sửa, không xóa)."""
from __future__ import annotations

from psycopg.types.json import Jsonb


async def audit(conn, actor: str, action: str, entity: str, entity_id: str, before=None, after=None) -> None:
    await conn.execute(
        "INSERT INTO audit_logs (actor, action, entity, entity_id, before, after) VALUES (%s, %s, %s, %s, %s, %s)",
        (actor, action, entity, entity_id,
         Jsonb(before) if before is not None else None,
         Jsonb(after) if after is not None else None),
    )
