"""Thử tải và đọc một kỳ từ một nguồn, không lưu gì. Dùng cho lệnh probe-source và trang quản trị."""
from __future__ import annotations

from ..collector.planner import parse_draw_id
from ..db import load_structure
from ..domain.prizes import is_complete, normalize, ordered, validate
from ..sources.base import DrawRef
from ..sources.registry import build


async def probe(ctx, code: str, draw_id: str) -> dict:
    out: dict = {"source": code, "draw_id": draw_id, "ok": False}
    async with ctx.pool.connection() as conn:
        src = await (await conn.execute("SELECT * FROM data_sources WHERE code = %s", (code,))).fetchone()
        if not src:
            return {**out, "error": f"Không có nguồn {code}"}
        try:
            region, province, day = parse_draw_id(draw_id)
        except ValueError:
            return {**out, "error": "Mã kỳ quay phải có dạng <miền>-<đài>-<YYYY-MM-DD>"}
        p = await (await conn.execute("SELECT game FROM provinces WHERE code = %s", (province,))).fetchone()
        structure = await load_structure(conn, region, day)
    adapter = build(src, ctx.settings)
    if not adapter:
        return {**out, "error": f"Nguồn {code} không có bộ chuyển đổi tải tự động"}
    ref = DrawRef(draw_id, p["game"] if p else "xs", region, province, day)
    try:
        res = await adapter.fetch(ctx.http, ref)
    except Exception as e:  # noqa: BLE001
        return {**out, "error": f"Lỗi khi tải: {type(e).__name__}: {e}"}
    out.update(url=res.url, http_status=res.status, bytes=len(res.body))
    if not res.body:
        return {**out, "error": "Nguồn chưa có dữ liệu cho kỳ này"}
    try:
        parsed = adapter.parse(res, ref)
    except Exception as e:  # noqa: BLE001
        return {**out, "error": f"Lỗi khi đọc: {type(e).__name__}: {e}"}
    prizes = ordered(structure, normalize(parsed.prizes, adapter.prize_map))
    if not prizes:
        return {**out, "error": "Không tìm thấy kết quả của ngày này trong trang"}
    complete = is_complete(structure, prizes)
    errs = validate(structure, prizes, partial=not complete)
    return {**out, "ok": complete and not errs, "complete": complete, "errors": errs, "meta": parsed.meta,
            "prizes": [{"code": s.code, "name": s.name, "numbers": prizes.get(s.code, [])} for s in structure.prizes]}
