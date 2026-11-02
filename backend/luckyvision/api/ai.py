"""API AI: /v1/ai/status, /v1/ai/ask, /v1/ai/pick. Cần ANTHROPIC_API_KEY trong .env."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..ai import LIMITER, SYSTEM_ASK, SYSTEM_PICK, AiError, complete, parse_pick, pick_rule, stats_context
from .errors import ApiError

router = APIRouter(prefix="/v1/ai", tags=["ai"])
DISCLAIMER = "Nội dung do AI tạo, chỉ để tham khảo và giải trí. Mỗi kỳ quay là ngẫu nhiên; không bộ số nào dễ trúng hơn."


def _guard(request: Request) -> None:
    s = request.app.state.settings
    if not s.anthropic_api_key:
        raise ApiError(503, "ai_disabled", "Tính năng AI chưa bật (thiếu ANTHROPIC_API_KEY)")
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not LIMITER.allow(ip, s.ai_requests_per_minute):
        raise ApiError(429, "rate_limited", "Bạn hỏi hơi nhanh, thử lại sau ít phút", headers={"Retry-After": "60"})


@router.get("/status")
async def status(request: Request):
    s = request.app.state.settings
    return {"enabled": bool(s.anthropic_api_key), "model": s.ai_model if s.anthropic_api_key else None}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    region: str = Field(pattern=r"^(mb|mn|mt|vl)$")
    province: str | None = None


@router.post("/ask")
async def ask(request: Request, body: AskIn):
    _guard(request)
    async with request.app.state.pool.connection() as conn:
        ctx = await stats_context(conn, body.region, body.province)
    user = f"DỮ LIỆU:\n{json.dumps(ctx, ensure_ascii=False)}\n\nCÂU HỎI: {body.question}"
    try:
        answer = await complete(request.app.state.settings, request.app.state.collector.http, SYSTEM_ASK, user)
    except AiError as e:
        raise ApiError(502, "ai_error", str(e))
    return {"answer": answer, "data_used": {"draws_analyzed": ctx["draws_analyzed"]}, "disclaimer": DISCLAIMER}


class PickIn(BaseModel):
    region: str = Field(pattern=r"^(mb|mn|mt|vl)$")
    province: str | None = None
    preferences: str = Field("", max_length=400)
    count: int = Field(3, ge=1, le=5)
    size: int = Field(5, ge=2, le=10, description="Số lượng số lô mỗi bộ (xổ số truyền thống)")


@router.post("/pick")
async def pick(request: Request, body: PickIn):
    _guard(request)
    game = "power655" if body.region == "vl" else "xs"
    async with request.app.state.pool.connection() as conn:
        ctx = await stats_context(conn, body.region, body.province)
    user = (f"Số liệu tham khảo (không dùng để hứa trúng): {json.dumps({k: ctx[k] for k in ('hot_last_30', 'longest_gaps')}, ensure_ascii=False)}\n"
            f"Mong muốn của người dùng: {body.preferences or 'không có, chọn ngẫu nhiên cho vui'}\n"
            f"Hãy tạo {body.count} bộ số.")
    system = SYSTEM_PICK.replace("{rule}", pick_rule(game, body.size))
    try:
        text = await complete(request.app.state.settings, request.app.state.collector.http, system, user, 700)
        sets = parse_pick(text, game, body.size, body.count)
    except AiError as e:
        raise ApiError(502, "ai_error", str(e))
    return {"sets": sets, "game": game, "disclaimer": DISCLAIMER}
