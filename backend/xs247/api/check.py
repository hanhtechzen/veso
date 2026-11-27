"""Dò vé giấy công khai: POST /v1/check-ticket. Không đăng nhập, không ghi DB, giới hạn 30 lần/phút theo IP."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from ..ai import RateLimiter
from ..domain.games import GAMES
from ..domain.play import check_ticket, validate_ticket
from ..domain.play import LOTTO_SLOTS
from ..play_service import draw_id_for, lotto_draw_id, published_prizes, resolve_lotto_draw
from .errors import ApiError

router = APIRouter(prefix="/v1", tags=["check"])
LIMIT = RateLimiter()
PER_MINUTE = 30
MAX_LINES = {"xs": 5, "power655": 6, "mega645": 6, "lotto535": 6, "max3d": 6, "max3dpro": 6}


class CheckIn(BaseModel):
    game: str = Field(pattern=r"^(xs|power655|mega645|lotto535|max3d|max3dpro)$")
    province: str | None = Field(None, max_length=40)
    draw_date: date
    lines: list[Any] = Field(min_length=1, max_length=6)
    slot: str | None = Field(None, max_length=5)   # Lotto 5/35: "13:00" hoặc "21:00"


@router.post("/check-ticket")
async def check_ticket_public(request: Request, response: Response, body: CheckIn):
    response.headers["Cache-Control"] = "no-store"
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not LIMIT.allow(ip, PER_MINUTE):
        raise ApiError(429, "rate_limited", "Bạn dò hơi nhanh, thử lại sau ít phút", headers={"Retry-After": "60"})
    if len(body.lines) > MAX_LINES[body.game]:
        raise ApiError(422, "invalid_ticket", f"Tối đa {MAX_LINES[body.game]} dòng")
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
            lines = [validate_ticket(body.game, region, [ln] if body.game in ("xs", "max3d") and not isinstance(ln, list) else ln) for ln in body.lines]
        except ValueError as e:
            raise ApiError(422, "invalid_ticket", str(e))
        if body.game == "lotto535":
            # Lotto quay 2 kỳ/ngày, mã kỳ thật theo số kỳ: kỳ thứ nhất trong ngày = 13:00, thứ hai = 21:00
            if body.slot not in LOTTO_SLOTS:
                raise ApiError(422, "invalid_ticket", "Chọn kỳ quay 13:00 hoặc 21:00")
            rows = await (await conn.execute(
                """SELECT id, draw_seq, current_version FROM lottery_draws
                    WHERE game = 'lotto535' AND draw_date = %s AND draw_seq IS NOT NULL""",
                (body.draw_date,))).fetchall()
            d = resolve_lotto_draw(list(rows), body.slot)
            did = d["id"] if d else lotto_draw_id(body.draw_date, body.slot)
            if not d and body.draw_date < date.today():
                raise ApiError(404, "draw_not_found", "Chưa có kỳ quay này")
        else:
            did = draw_id_for(body.game, region, province, body.draw_date)
            d = await (await conn.execute(
                """SELECT id, game, region_code, province_code, draw_date, scheduled_at, current_version, status
                     FROM lottery_draws WHERE id = %s""", (did,))).fetchone()
            if not d:
                raise ApiError(404, "draw_not_found", "Chưa có kỳ quay này")
        prizes = None
        if d and d.get("current_version") is not None:
            prizes = (await published_prizes(conn, [did])).get(did)
    published = bool(prizes)
    return {
        "draw": {"id": did, "draw_date": body.draw_date.isoformat(), "province": province, "region": region,
                 "game": body.game},
        "published": published,
        "lines": [{"numbers": n, "result": check_ticket(body.game, region, n, prizes) if published else None}
                  for n in lines],
    }
