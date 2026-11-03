"""Ghi nhận lượt xem trang: POST /v1/t (gửi bằng navigator.sendBeacon từ /assets/lv-track.js)."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Request, Response

from ..ai import RateLimiter
from ..analytics import device_of, is_bot, new_salt, normalize_path, source_of, visitor_id
from ..config import VN_TZ

router = APIRouter(prefix="/v1", tags=["analytics"], include_in_schema=False)
LIMIT = RateLimiter()
_SALTS: dict[str, str] = {}


async def _salt(request: Request, day: str) -> str:
    """Muối dùng chung giữa các tiến trình qua Redis, tự hết hạn sau 2 ngày (không thể tính lại mã khách cũ)."""
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            key = f"lv:salt:{day}"
            await redis.set(key, new_salt(), nx=True, ex=2 * 86400)
            v = await redis.get(key)
            if v:
                return v.decode() if isinstance(v, bytes) else v
        except Exception:  # noqa: BLE001
            pass
    if day not in _SALTS:
        _SALTS.clear()
        _SALTS[day] = new_salt()
    return _SALTS[day]


@router.post("/t", status_code=204)
async def track(request: Request):
    ua = request.headers.get("user-agent", "")
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "")
    if is_bot(ua) or request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return Response(status_code=204)
    if not LIMIT.allow(f"t:{ip}", 120):
        return Response(status_code=204)
    try:
        data = json.loads((await request.body())[:2000] or b"{}")
    except ValueError:
        return Response(status_code=204)
    path = normalize_path(data.get("p", ""))
    if not path:
        return Response(status_code=204)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    source = source_of(str(data.get("r", ""))[:500], host)
    now = datetime.now(VN_TZ)
    day = now.date()
    vid = visitor_id(await _salt(request, day.isoformat()), ip, ua)
    async with request.app.state.pool.connection() as conn:
        await conn.execute("""INSERT INTO page_views_daily (day, path, views) VALUES (%s, %s, 1)
                              ON CONFLICT (day, path) DO UPDATE SET views = page_views_daily.views + 1""", (day, path))
        row = await (await conn.execute("""INSERT INTO visitors_daily (day, visitor, device) VALUES (%s, %s, %s)
                              ON CONFLICT (day, visitor) DO UPDATE SET pages = visitors_daily.pages + 1
                              RETURNING (xmax = 0) AS is_new""", (day, vid, device_of(ua)))).fetchone()
        if row and row["is_new"]:
            # Nguồn chỉ tính ở lần xem đầu tiên trong ngày của mỗi khách
            await conn.execute("""INSERT INTO referrers_daily (day, source, views) VALUES (%s, %s, 1)
                                  ON CONFLICT (day, source) DO UPDATE SET views = referrers_daily.views + 1""",
                               (day, source or "(Vào trực tiếp)"))
    return Response(status_code=204)
