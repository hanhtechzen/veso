"""Bước 2–7: chuẩn hóa, kiểm tra, lưu ứng viên, đối chiếu, công bố (mục 4 tài liệu thiết kế)."""
from __future__ import annotations

import logging

from psycopg.types.json import Jsonb

from ..audit import audit
from ..config import Settings
from ..db import load_structure
from ..domain.prizes import checksum, is_complete, new_numbers, normalize, ordered, validate
from ..domain.reconcile import Candidate, reconcile
from ..events import emit

log = logging.getLogger(__name__)


class AlreadyPublishedError(ValueError):
    """Ứng viên trùng nội dung với phiên bản đang công bố."""


async def get_draw(conn, draw_id: str, lock: bool = False) -> dict | None:
    cur = await conn.execute("SELECT * FROM lottery_draws WHERE id = %s" + (" FOR UPDATE" if lock else ""), (draw_id,))
    return await cur.fetchone()


async def ingest(conn, settings: Settings, draw_id: str, source_code: str, raw_prizes: dict,
                 *, fetch_id: int | None = None, prize_map: dict | None = None,
                 source_complete: bool | None = None, created_by: str | None = None) -> dict:
    """Đưa một bản kết quả (đầy đủ hoặc đang quay dở) của một nguồn vào hệ thống.

    Trả về {"status": ..., "alerts": [(mức, nội dung)], "candidate_id": ...}.
    """
    out: dict = {"status": "ignored", "alerts": [], "candidate_id": None}
    draw = await get_draw(conn, draw_id, lock=True)
    if not draw:
        out["status"] = "unknown_draw"
        return out
    structure = await load_structure(conn, draw["region_code"], draw["draw_date"])
    prizes = ordered(structure, normalize(raw_prizes, prize_map))
    complete = is_complete(structure, prizes) if source_complete is None else (source_complete and is_complete(structure, prizes))
    errors = validate(structure, prizes, partial=not complete)

    async def mark_fetch(status: str, err: str | None = None):
        if fetch_id:
            await conn.execute("UPDATE raw_fetches SET parse_status = %s, error = %s WHERE id = %s", (status, err, fetch_id))

    if errors:
        await mark_fetch("invalid", "; ".join(errors)[:1000])
        out["status"] = "invalid"
        out["errors"] = errors
        if is_complete(structure, prizes) and draw["status"] not in ("published", "needs_review"):
            await conn.execute("UPDATE lottery_draws SET status = 'needs_review', updated_at = now() WHERE id = %s", (draw_id,))
            await audit(conn, "system", "validation_failed", "lottery_draws", draw_id, None,
                        {"source": source_code, "errors": errors})
            out["alerts"].append(("warn", f"{draw_id}: nguồn {source_code} trả kết quả sai cơ cấu giải."))
        return out
    if not prizes:
        await mark_fetch("partial")
        out["status"] = "empty"
        return out

    # Các số đã được thông báo (từ mọi nguồn), để không phát trùng sự kiện prize.updated
    cur = await conn.execute(
        "SELECT payload FROM result_candidates WHERE draw_id = %s AND source_code <> 'manual'", (draw_id,))
    seen: dict[tuple[str, int], set[str]] = {}
    for r in await cur.fetchall():
        for code, nums in r["payload"].items():
            for i, n in enumerate(nums):
                seen.setdefault((code, i), set()).add(n)
    cur = await conn.execute(
        """INSERT INTO result_candidates (draw_id, source_code, fetch_id, payload, is_complete, checksum, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (draw_id, source_code, checksum) DO NOTHING RETURNING id""",
        (draw_id, source_code, fetch_id, Jsonb(prizes), complete, checksum(prizes), created_by))
    ins = await cur.fetchone()
    await mark_fetch("ok" if complete else "partial")
    if ins:
        out["candidate_id"] = ins["id"]
    else:  # trùng nội dung: trả về ứng viên đã có
        cur = await conn.execute(
            "SELECT id FROM result_candidates WHERE draw_id = %s AND source_code = %s AND checksum = %s",
            (draw_id, source_code, checksum(prizes)))
        existing = await cur.fetchone()
        out["candidate_id"] = existing["id"] if existing else None
    region = draw["region_code"]
    base = {"draw_id": draw_id, "region": region, "province": draw["province_code"]}

    if ins and draw["current_version"] is None and source_code != "manual":
        if draw["status"] == "scheduled":
            await conn.execute("UPDATE lottery_draws SET status = 'collected', updated_at = now() WHERE id = %s", (draw_id,))
            draw["status"] = "collected"
            await emit(conn, "draw.started", region, base)
        for prize, idx, number in new_numbers(None, prizes):
            if number in seen.get((prize, idx), ()):
                continue
            await emit(conn, "prize.updated", region,
                       {**base, "prize": prize, "index": idx, "number": number, "source": source_code, "provisional": True})
    if complete and draw["status"] == "collected":
        await conn.execute("UPDATE lottery_draws SET status = 'validated', updated_at = now() WHERE id = %s", (draw_id,))
        draw["status"] = "validated"
        await emit(conn, "draw.completed", region, {**base, "status": "validated"})
    out["status"] = "complete" if complete else "partial"
    if complete and source_code != "manual":
        out["alerts"] += await try_verify(conn, settings, draw)
    return out


async def load_candidates(conn, draw_id: str) -> list[Candidate]:
    cur = await conn.execute(
        """SELECT c.id, c.source_code, s.priority, c.checksum, c.is_complete, c.payload
             FROM result_candidates c JOIN data_sources s ON s.code = c.source_code
            WHERE c.draw_id = %s ORDER BY c.id""", (draw_id,))
    return [Candidate(r["id"], r["source_code"], r["priority"], r["checksum"], r["is_complete"], r["payload"])
            for r in await cur.fetchall()]


async def try_verify(conn, settings: Settings, draw: dict) -> list[tuple[str, str]]:
    alerts: list[tuple[str, str]] = []
    draw_id = draw["id"]
    decision = reconcile(await load_candidates(conn, draw_id), settings.min_sources(draw["region_code"]))
    if decision.outcome == "verified":
        if draw["current_version"] is None:
            if settings.auto_verify:
                actor = "auto:two-source-match" if len(decision.sources) > 1 else f"auto:{decision.sources[0]}"
                await publish(conn, draw_id, decision.candidate_id, actor,
                              reason="Khớp " + ", ".join(decision.sources))
            elif draw["status"] != "verified":
                await conn.execute("UPDATE lottery_draws SET status = 'verified', updated_at = now() WHERE id = %s", (draw_id,))
                alerts.append(("info", f"{draw_id}: hai nguồn đã khớp, chờ quản trị duyệt công bố."))
        else:
            cur = await conn.execute(
                """SELECT c.checksum FROM draw_versions v JOIN result_candidates c ON c.id = v.candidate_id
                    WHERE v.draw_id = %s AND v.version = %s""", (draw_id, draw["current_version"]))
            pub = await cur.fetchone()
            win = next(c for c in await load_candidates(conn, draw_id) if c.id == decision.candidate_id)
            if pub and pub["checksum"] != win.checksum and draw["status"] != "needs_review":
                await conn.execute("UPDATE lottery_draws SET status = 'needs_review', updated_at = now() WHERE id = %s", (draw_id,))
                await audit(conn, "system", "differs_from_published", "lottery_draws", draw_id, None,
                            {"sources": decision.sources})
                alerts.append(("critical", f"{draw_id}: các nguồn hiện khớp nhau nhưng KHÁC bản đã công bố. Cần kiểm tra."))
    elif decision.outcome == "conflict" and draw["status"] not in ("needs_review",):
        await conn.execute("UPDATE lottery_draws SET status = 'needs_review', updated_at = now() WHERE id = %s", (draw_id,))
        await audit(conn, "system", "sources_conflict", "lottery_draws", draw_id, None,
                    {"sources": decision.sources, "differences": decision.differences[:20]})
        alerts.append(("warn", f"{draw_id}: các nguồn lệch nhau ({len(decision.differences)} chỗ). Cần quản trị xử lý."))
    return alerts


async def publish(conn, draw_id: str, candidate_id: int, actor: str, reason: str | None = None) -> int:
    """Công bố một ứng viên thành phiên bản mới (không ghi đè phiên bản cũ)."""
    draw = await get_draw(conn, draw_id, lock=True)
    if not draw:
        raise ValueError("Không có kỳ quay")
    cur = await conn.execute("SELECT payload, checksum FROM result_candidates WHERE id = %s AND draw_id = %s", (candidate_id, draw_id))
    cand = await cur.fetchone()
    if not cand:
        raise ValueError("Ứng viên không thuộc kỳ quay này")
    if draw["current_version"] is not None:
        cur = await conn.execute(
            """SELECT c.checksum FROM draw_versions v JOIN result_candidates c ON c.id = v.candidate_id
                WHERE v.draw_id = %s AND v.version = %s""", (draw_id, draw["current_version"]))
        pub = await cur.fetchone()
        if pub and pub["checksum"] == cand["checksum"]:
            raise AlreadyPublishedError("Ứng viên trùng phiên bản đang công bố")
    cur = await conn.execute("SELECT coalesce(max(version), 0) + 1 AS v FROM draw_versions WHERE draw_id = %s", (draw_id,))
    version = (await cur.fetchone())["v"]
    await conn.execute("UPDATE draw_versions SET status = 'superseded' WHERE draw_id = %s AND status = 'published'", (draw_id,))
    await conn.execute(
        """INSERT INTO draw_versions (draw_id, version, status, candidate_id, reason, created_by, verified_by, verified_at)
           VALUES (%s, %s, 'published', %s, %s, %s, %s, now())""",
        (draw_id, version, candidate_id, reason, actor, actor))
    rows = [(draw_id, version, code, i, n) for code, nums in cand["payload"].items() for i, n in enumerate(nums)]
    async with conn.cursor() as c:
        await c.executemany(
            "INSERT INTO lottery_results (draw_id, version, prize_code, position, number) VALUES (%s, %s, %s, %s, %s)", rows)
    await conn.execute(
        """UPDATE lottery_draws SET status = 'published', current_version = %s,
                  published_at = coalesce(published_at, now()), updated_at = now() WHERE id = %s""",
        (version, draw_id))
    await audit(conn, actor, "publish", "lottery_draws", draw_id,
                {"version": draw["current_version"], "status": draw["status"]},
                {"version": version, "candidate_id": candidate_id, "reason": reason})
    topic = "draw.published" if version == 1 else "draw.corrected"
    await emit(conn, topic, draw["region_code"],
               {"draw_id": draw_id, "region": draw["region_code"], "province": draw["province_code"], "version": version})
    return version
