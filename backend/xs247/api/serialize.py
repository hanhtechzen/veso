"""Chuyển dữ liệu kỳ quay sang JSON trả về cho API (mục 6 tài liệu thiết kế)."""
from __future__ import annotations

from ..config import VN_TZ
from ..db import load_structure
from ..domain.prizes import loto


def iso(dt):
    return dt.astimezone(VN_TZ).isoformat() if dt else None


async def results_for(conn, keys: list[tuple[str, int]]) -> dict[str, dict[str, list[str]]]:
    if not keys:
        return {}
    cur = await conn.execute(
        """SELECT r.draw_id, r.prize_code, r.number FROM lottery_results r
             JOIN unnest(%s::text[], %s::int[]) AS k(draw_id, version)
               ON k.draw_id = r.draw_id AND k.version = r.version
            ORDER BY r.draw_id, r.prize_code, r.position""",
        ([k[0] for k in keys], [k[1] for k in keys]))
    out: dict[str, dict[str, list[str]]] = {}
    for r in await cur.fetchall():
        out.setdefault(r["draw_id"], {}).setdefault(r["prize_code"], []).append(r["number"])
    return out


async def draw_json(conn, d: dict, prizes: dict[str, list[str]] | None, *, detail: bool = False,
                    province_names: dict[str, str] | None = None) -> dict:
    structure = await load_structure(conn, d["region_code"], d["draw_date"])
    pz = prizes or {}
    out = {
        "id": d["id"],
        "region": d["region_code"],
        "province": {"code": d["province_code"], "name": (province_names or {}).get(d["province_code"])},
        "draw_date": d["draw_date"].isoformat(),
        "draw_time": iso(d["scheduled_at"]),
        "draw_seq": d.get("draw_seq"),
        "status": d["status"],
        "version": d["current_version"],
        "prizes": [{"code": s.code, "name": s.name, "numbers": pz.get(s.code, [])} for s in structure.prizes],
        "published_at": iso(d.get("published_at")),
    }
    if structure.game == "xs":
        out["loto"] = loto({s.code: pz.get(s.code, []) for s in structure.prizes})
    if detail and d["current_version"]:
        cur = await conn.execute(
            """SELECT v.created_by, v.verified_by, v.verified_at, v.reason, c.checksum
                 FROM draw_versions v LEFT JOIN result_candidates c ON c.id = v.candidate_id
                WHERE v.draw_id = %s AND v.version = %s""", (d["id"], d["current_version"]))
        v = await cur.fetchone()
        cur = await conn.execute(
            """SELECT DISTINCT ON (source_code) source_code, created_at FROM result_candidates
                WHERE draw_id = %s AND checksum = %s AND is_complete AND source_code <> 'manual'
                ORDER BY source_code, created_at""", (d["id"], v["checksum"] if v else None))
        out["sources"] = [{"code": r["source_code"], "fetched_at": iso(r["created_at"])} for r in await cur.fetchall()]
        out["verified_by"] = v["verified_by"] if v else None
        out["verified_at"] = iso(v["verified_at"]) if v else None
    return out


async def province_names(conn) -> dict[str, str]:
    cur = await conn.execute("SELECT code, name FROM provinces")
    return {r["code"]: r["name"] for r in await cur.fetchall()}
