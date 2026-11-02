"""API công khai: kết quả, lịch quay, ảnh chụp kỳ đang quay."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Query, Request, Response

from ..config import VN_TZ
from .errors import ApiError
from .serialize import draw_json, iso, province_names, results_for

router = APIRouter(prefix="/v1", tags=["public"])
REGIONS = {"mb", "mn", "mt", "vl"}


def _region(region: str | None) -> None:
    if region and region not in REGIONS:
        raise ApiError(400, "invalid_param", "region phải là một trong mb, mn, mt, vl")


@router.get("/provinces")
async def provinces(request: Request, response: Response):
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT p.code, p.name, p.region_code, p.game,
                      array_agg(DISTINCT s.iso_weekday ORDER BY s.iso_weekday) FILTER (WHERE s.id IS NOT NULL) AS weekdays,
                      min(s.draw_time) AS draw_time
                 FROM provinces p LEFT JOIN draw_schedules s ON s.province_code = p.code
                     AND (s.valid_to IS NULL OR s.valid_to >= current_date)
                WHERE p.active GROUP BY p.code ORDER BY p.region_code, p.name""")).fetchall()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"items": [{"code": r["code"], "name": r["name"], "region": r["region_code"], "game": r["game"],
                       "weekdays": r["weekdays"] or [], "draw_time": r["draw_time"].strftime("%H:%M") if r["draw_time"] else None}
                      for r in rows]}


@router.get("/draws")
async def list_draws(request: Request, response: Response, region: str | None = None, province: str | None = None,
                     date_: date | None = Query(None, alias="date"), from_: date | None = Query(None, alias="from"),
                     to: date | None = None, limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    _region(region)
    q = ["SELECT * FROM lottery_draws WHERE current_version IS NOT NULL"]
    args: list = []
    for cond, val in (("region_code = %s", region), ("province_code = %s", province), ("draw_date = %s", date_),
                      ("draw_date >= %s", from_), ("draw_date <= %s", to)):
        if val is not None:
            q.append("AND " + cond); args.append(val)
    if cursor:
        try:
            cd, cid = cursor.split("|", 1)
            q.append("AND (draw_date, id) < (%s, %s)"); args += [date.fromisoformat(cd), cid]
        except ValueError:
            raise ApiError(400, "invalid_param", "cursor không hợp lệ")
    q.append("ORDER BY draw_date DESC, id DESC LIMIT %s"); args.append(limit + 1)
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(" ".join(q), args)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        res = await results_for(conn, [(r["id"], r["current_version"]) for r in rows])
        names = await province_names(conn)
        items = [await draw_json(conn, r, res.get(r["id"]), province_names=names) for r in rows]
    response.headers["Cache-Control"] = "public, max-age=60"
    nxt = f"{rows[-1]['draw_date'].isoformat()}|{rows[-1]['id']}" if more and rows else None
    return {"items": items, "next_cursor": nxt}


@router.get("/draws/latest")
async def latest(request: Request, response: Response, region: str):
    _region(region)
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT DISTINCT ON (province_code) * FROM lottery_draws
                WHERE region_code = %s AND current_version IS NOT NULL
                ORDER BY province_code, draw_date DESC""", (region,))).fetchall()
        if rows:
            top = max(r["draw_date"] for r in rows)
            rows = [r for r in rows if r["draw_date"] == top]
        res = await results_for(conn, [(r["id"], r["current_version"]) for r in rows])
        names = await province_names(conn)
        items = [await draw_json(conn, r, res.get(r["id"]), province_names=names) for r in rows]
    response.headers["Cache-Control"] = "public, max-age=10"
    return {"items": items}


@router.get("/draws/{draw_id}")
async def get_draw(request: Request, response: Response, draw_id: str):
    async with request.app.state.pool.connection() as conn:
        d = await (await conn.execute("SELECT * FROM lottery_draws WHERE id = %s AND current_version IS NOT NULL",
                                      (draw_id,))).fetchone()
        if not d:
            raise ApiError(404, "draw_not_found", "Không có kỳ quay này hoặc kỳ chưa được công bố")
        res = await results_for(conn, [(d["id"], d["current_version"])])
        out = await draw_json(conn, d, res.get(d["id"]), detail=True, province_names=await province_names(conn))
    etag = f'"{d["id"]}-v{d["current_version"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=86400" if d["status"] == "published" else "public, max-age=30"
    return out


@router.get("/schedule")
async def schedule(request: Request, response: Response, date_: date | None = Query(None, alias="date")):
    day = date_ or datetime.now(VN_TZ).date()
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT d.*, p.name AS province_name, (d.warn_at < now()) AS overdue
                 FROM lottery_draws d JOIN provinces p ON p.code = d.province_code
                WHERE d.draw_date = %s ORDER BY d.scheduled_at, d.id""", (day,))).fetchall()
    def state(r):
        if r["current_version"] is not None:
            return "published"
        if r["overdue"]:
            return "overdue"
        return "live" if r["status"] in ("collected", "validated", "verified") else "scheduled"
    response.headers["Cache-Control"] = "public, max-age=5"
    return {"date": day.isoformat(), "items": [
        {"id": r["id"], "region": r["region_code"], "province": {"code": r["province_code"], "name": r["province_name"]},
         "draw_time": iso(r["scheduled_at"]), "state": state(r), "status": r["status"]} for r in rows]}


@router.get("/live/{draw_id}")
async def live_snapshot(request: Request, response: Response, draw_id: str):
    async with request.app.state.pool.connection() as conn:
        d = await (await conn.execute("SELECT * FROM lottery_draws WHERE id = %s", (draw_id,))).fetchone()
        if not d:
            raise ApiError(404, "draw_not_found", "Không có kỳ quay này")
        if d["current_version"] is not None:
            res = await results_for(conn, [(d["id"], d["current_version"])])
            out = await draw_json(conn, d, res.get(d["id"]), province_names=await province_names(conn))
            out["provisional"] = False
        else:
            c = await (await conn.execute(
                """SELECT c.payload FROM result_candidates c JOIN data_sources s ON s.code = c.source_code
                    WHERE c.draw_id = %s AND c.source_code <> 'manual'
                    ORDER BY (SELECT count(*) FROM jsonb_each(c.payload) e, jsonb_array_elements(e.value)) DESC,
                             s.priority, c.id DESC LIMIT 1""", (draw_id,))).fetchone()
            out = await draw_json(conn, d, c["payload"] if c else {}, province_names=await province_names(conn))
            out["provisional"] = True
    out["last_event_id"] = None
    response.headers["Cache-Control"] = "no-store"
    return out
