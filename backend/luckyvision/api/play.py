"""Chơi thử: /v1/play/*. Vé thử của thành viên (không phải mua vé thật), tự dò khi kỳ quay có kết quả.

Hạn mức 10 vé mỗi thành viên mỗi ngày Việt Nam, tính cả vé đã hủy. Đếm và thêm vé nằm trong cùng một giao dịch,
sau khi khóa hàng thành viên (SELECT ... FOR UPDATE) nên hai yêu cầu song song không vượt hạn mức.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..ai import AiError, complete
from ..domain.play_stats import ai_prompt, sanitize_comment, summarize
from ..collector.planner import day_slots, make_draw_id
from ..config import VN_TZ
from ..domain.games import GAMES
from ..domain.play import LOTTO_SLOTS, closes_at, validate_ticket
from ..play_service import (published_prizes, DAILY_LIMIT, HORIZON_DAYS, check_rows, draw_id_for, lotto_draw_id,
                            lotto_scheduled_at, open_draws, prize_key, resolve_lotto_rows)
from .errors import ApiError
from .user import need_user

router = APIRouter(prefix="/v1/play", tags=["play"])
NO_STORE = "private, no-store"


def now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _count(row) -> int:
    return int(row["n"]) if row is not None else 0


async def _used_today(conn, user_id: int, day: date) -> int:
    row = await (await conn.execute(
        "SELECT count(*) AS n FROM play_tickets WHERE user_id = %s AND play_day = %s", (user_id, day))).fetchone()
    return _count(row)


def _public(t: dict) -> dict:
    sched = t.get("scheduled_at")
    close = t.get("closes_at") or (closes_at(sched, t["game"]) if sched else None)
    can_cancel = (not t.get("cancelled_at") and t.get("current_version") is None and close is not None and now() < close)
    return {"id": t["id"], "game": t["game"], "province": t.get("province_code"), "region": t.get("region_code"),
            "draw_id": t["draw_id"], "draw_date": _iso(t.get("draw_date")), "numbers": list(t["numbers"]),
            "scheduled_at": _iso(sched), "closes_at": _iso(close), "created_at": _iso(t.get("created_at")),
            "result": t.get("result"), "checked_version": t.get("checked_version"), "can_cancel": bool(can_cancel),
            "draw_result": _draw_result(t)}


def _draw_result(t: dict) -> dict | None:
    """Kết quả kỳ quay để hiện cạnh vé (kiểu Vietlott: một hàng số trúng thưởng, một hàng vé của bạn).
    Vietlott: {"main": [...], "special": [...]}. Vé 3 miền: các số trúng khớp với vé {"hits": [{code, number}]}."""
    pr = t.get("_prizes")
    if not pr:
        return None
    if t["game"] in ("max3d", "max3dpro"):
        return {c: list(pr.get(c, [])) for c in ("db", "g1", "g2", "g3")}
    if t["game"] != "xs":
        return {"main": list(pr.get("main", [])), "special": list(pr.get("special", []))}
    ticket = (list(t["numbers"]) or [""])[0]
    hits = []
    for code, nums in pr.items():
        for n in nums:
            if n and ticket.endswith(n):
                hits.append({"code": code, "number": n})
    db = (pr.get("db") or [""])[0]
    return {"hits": hits, "db": db}


class TicketIn(BaseModel):
    game: str = Field(pattern=r"^(xs|power655|mega645|lotto535|max3d|max3dpro)$")
    province: str | None = Field(None, max_length=40)
    draw_date: date
    slot: str | None = Field(None, max_length=10)       # chỉ Lotto 5/35: "13:00" hoặc "21:00"
    numbers: list[Any] = Field(max_length=12)


async def _find_draw(conn, game: str, region: str, province: str, day: date) -> dict | None:
    """Kỳ quay theo mã; nếu chưa được lập lịch thì dựng từ lịch quay (và ngày nghỉ)."""
    did = make_draw_id(region, province, day)
    d = await (await conn.execute(
        """SELECT id, game, region_code, province_code, draw_date, scheduled_at, current_version, status
             FROM lottery_draws WHERE id = %s""", (did,))).fetchone()
    if d:
        return d
    for s in await day_slots(conn, day):
        if s["province_code"] == province and s["region_code"] == region:
            return {"id": did, "game": game, "region_code": region, "province_code": province, "draw_date": day,
                    "scheduled_at": datetime.combine(day, s["draw_time"], VN_TZ), "current_version": None, "status": "scheduled"}
    return None


@router.post("/tickets", status_code=201)
async def create_ticket(request: Request, response: Response, body: TicketIn, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    t_now = now()
    today = t_now.astimezone(VN_TZ).date()
    async with request.app.state.pool.connection() as conn:
        if body.game == "xs":
            if not body.province:
                raise ApiError(422, "invalid_ticket", "Chọn đài hoặc miền")
            p = await (await conn.execute(
                "SELECT code, name, region_code, game, active FROM provinces WHERE code = %s", (body.province,))).fetchone()
            if not p or not p["active"] or p["game"] != "xs" or p["region_code"] not in ("mb", "mn", "mt"):
                raise ApiError(422, "invalid_ticket", "Đài không hợp lệ")
            region, province = p["region_code"], p["code"]
        else:
            region, province = GAMES[body.game].region, body.game
        try:
            numbers = validate_ticket(body.game, region, body.numbers)
        except ValueError as e:
            raise ApiError(422, "invalid_ticket", str(e))
        if body.game == "lotto535" and body.slot not in LOTTO_SLOTS:
            raise ApiError(422, "invalid_ticket", "Chọn kỳ quay 13:00 hoặc 21:00")
        draw = None
        if (body.draw_date - today).days <= HORIZON_DAYS:
            if body.game == "lotto535":
                draw = {"id": lotto_draw_id(body.draw_date, body.slot), "game": body.game, "region_code": region,
                        "province_code": province, "draw_date": body.draw_date,
                        "scheduled_at": lotto_scheduled_at(body.draw_date, body.slot), "current_version": None,
                        "status": "scheduled"}
            else:
                draw = await _find_draw(conn, body.game, region, province, body.draw_date)
        if not draw:
            raise ApiError(422, "draw_not_found", "Không có kỳ quay này trong 7 ngày tới")
        close = closes_at(draw["scheduled_at"], body.game)
        if draw.get("current_version") is not None or t_now >= close:
            raise ApiError(422, "draw_closed", "Kỳ quay đã đóng nhận vé")
        # khóa hàng thành viên để đếm + thêm là một bước nguyên tử
        await conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (u["id"],))
        used = await _used_today(conn, u["id"], today)
        if used >= DAILY_LIMIT:
            raise ApiError(429, "daily_limit", f"Mỗi ngày tối đa {DAILY_LIMIT} vé chơi thử")
        row = await (await conn.execute(
            """INSERT INTO play_tickets (user_id, game, region_code, province_code, draw_date, draw_id, numbers, closes_at, play_day)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (u["id"], body.game, region, province, body.draw_date,
             draw["id"] if body.game == "lotto535" else draw_id_for(body.game, region, province, body.draw_date),
             numbers, close, today))).fetchone()
    t = {**row, "scheduled_at": draw["scheduled_at"], "current_version": draw.get("current_version")}
    return {"ticket": _public(t), "remaining_today": DAILY_LIMIT - used - 1}


@router.get("/tickets")
async def list_tickets(request: Request, response: Response, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT t.*, d.scheduled_at, d.current_version, d.status AS draw_status
                 FROM play_tickets t LEFT JOIN lottery_draws d ON d.id = t.draw_id
                WHERE t.user_id = %s AND t.cancelled_at IS NULL ORDER BY t.created_at DESC, t.id DESC LIMIT 100""",
            (u["id"],))).fetchall()
        rows = [dict(r) for r in rows]
        await resolve_lotto_rows(conn, rows)
        await check_rows(conn, rows)
        pub = sorted({prize_key(r) for r in rows if r.get("current_version") is not None})
        prizes = await published_prizes(conn, pub) if pub else {}
        for r in rows:
            r["_prizes"] = prizes.get(prize_key(r))
    return {"tickets": [_public(r) for r in rows]}


_AI_USED: dict[tuple[int, date], int] = {}
AI_DAILY_LIMIT = 3
AI_DISCLAIMER = "Nội dung do AI tạo, chỉ để tham khảo và giải trí. Mỗi kỳ quay là ngẫu nhiên; không bộ số nào dễ trúng hơn."
STATS_SYSTEM = (
    "Bạn là trợ lý thân thiện của LuckyVision, trả lời bằng tiếng Việt, ngắn gọn. Chỉ nhận xét thói quen chơi dựa trên "
    "số liệu được cung cấp; không bịa số liệu, không gợi ý số, không hứa hẹn trúng thưởng."
)


async def _my_stats(conn, user_id: int) -> dict:
    rows = await (await conn.execute(
        """SELECT t.*, d.scheduled_at, d.current_version, d.status AS draw_status
             FROM play_tickets t LEFT JOIN lottery_draws d ON d.id = t.draw_id
            WHERE t.user_id = %s AND t.cancelled_at IS NULL ORDER BY t.created_at DESC, t.id DESC LIMIT 500""",
        (user_id,))).fetchall()
    rows = [dict(r) for r in rows]
    await check_rows(conn, rows)
    return summarize([{"game": r["game"], "region": r.get("region_code"), "numbers": r["numbers"],
                       "draw_date": r.get("draw_date"), "cancelled_at": r.get("cancelled_at"), "result": r.get("result")}
                      for r in rows])


@router.get("/stats")
async def my_stats(request: Request, response: Response, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    async with request.app.state.pool.connection() as conn:
        stats = await _my_stats(conn, u["id"])
    return {"stats": stats}


@router.post("/stats/ai")
async def my_stats_ai(request: Request, response: Response, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    settings = request.app.state.settings
    if not settings.ai_enabled:
        raise ApiError(503, "ai_disabled", "Tính năng AI chưa bật")
    async with request.app.state.pool.connection() as conn:
        stats = await _my_stats(conn, u["id"])
    if stats["total"] < 3:
        raise ApiError(422, "not_enough_tickets", "Cần ít nhất 3 vé chơi thử để nhận xét")
    today = now().astimezone(VN_TZ).date()
    for k in [k for k in _AI_USED if k[1] < today]:
        del _AI_USED[k]
    key = (u["id"], today)
    if _AI_USED.get(key, 0) >= AI_DAILY_LIMIT:
        raise ApiError(429, "ai_daily_limit", f"Mỗi ngày chỉ nhận xét tối đa {AI_DAILY_LIMIT} lần, mai quay lại nhé")
    _AI_USED[key] = _AI_USED.get(key, 0) + 1
    try:
        text = await complete(settings, request.app.state.collector.http, STATS_SYSTEM, ai_prompt(stats), 500)
    except AiError:
        _AI_USED[key] -= 1
        raise ApiError(502, "ai_error", "Trợ lý AI đang bận, bạn thử lại sau nhé")
    return {"comment": sanitize_comment(text), "disclaimer": AI_DISCLAIMER}


@router.delete("/tickets/{ticket_id}")
async def cancel_ticket(request: Request, response: Response, ticket_id: int, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    async with request.app.state.pool.connection() as conn:
        row = await (await conn.execute(
            """SELECT t.*, d.scheduled_at, d.current_version FROM play_tickets t LEFT JOIN lottery_draws d ON d.id = t.draw_id
                WHERE t.id = %s AND t.user_id = %s AND t.cancelled_at IS NULL""", (ticket_id, u["id"]))).fetchone()
        if not row or row["id"] != ticket_id or row["user_id"] != u["id"]:
            raise ApiError(404, "ticket_not_found", "Không có vé này")
        close = row.get("closes_at") or (closes_at(row["scheduled_at"], row["game"]) if row.get("scheduled_at") else None)
        if row.get("current_version") is not None or close is None or now() >= close:
            raise ApiError(422, "draw_closed", "Kỳ quay đã đóng, không thể hủy vé")
        await conn.execute(
            "UPDATE play_tickets SET cancelled_at = now() WHERE id = %s AND user_id = %s AND cancelled_at IS NULL",
            (ticket_id, u["id"]))
    return {"ok": True}


@router.get("/draws")
async def draws(request: Request, response: Response, u: dict = Depends(need_user)):
    response.headers["Cache-Control"] = NO_STORE
    t_now = now()
    async with request.app.state.pool.connection() as conn:
        items = await open_draws(conn, t_now)
        used = await _used_today(conn, u["id"], t_now.astimezone(VN_TZ).date())
    return {"draws": items, "remaining_today": max(0, DAILY_LIMIT - used), "daily_limit": DAILY_LIMIT}
