"""Form liên hệ: POST /v1/contact. Chống thư rác bằng ô bẫy ẩn, thời gian điền tối thiểu và giới hạn theo IP."""
from __future__ import annotations

import re
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..ai import RateLimiter
from ..alerts import send as send_alert
from .auth import client_ip
from .errors import ApiError
from .user import current_user

router = APIRouter(prefix="/v1", tags=["contact"])
LIMIT = RateLimiter()
TOPICS = {"quen-mat-khau": "Quên mật khẩu", "sai-ket-qua": "Báo sai kết quả", "gop-y": "Góp ý", "hop-tac": "Hợp tác, quảng cáo", "khac": "Khác"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-zA-Z]{2,}$")


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    phone: str = Field("", max_length=30)
    topic: str
    message: str = Field(min_length=5, max_length=3000)
    page: str = Field("", max_length=300)
    website: str = Field("", max_length=200)   # ô bẫy: người thật không thấy nên để trống
    t: int = 0                                # thời điểm mở form (mili giây)


@router.post("/contact", status_code=201)
async def contact(request: Request, body: ContactIn):
    if request.headers.get("x-lv-csrf") != "1":
        raise ApiError(403, "csrf", "Thiếu header X-LV-CSRF")
    if body.website:  # bot điền ô bẫy: giả vờ thành công
        return {"ok": True}
    if body.t and time.time() * 1000 - body.t < 3000:
        raise ApiError(429, "too_fast", "Bạn gửi hơi nhanh, hãy thử lại sau vài giây")
    if not LIMIT.allow(f"contact:{client_ip(request)}", 5, window=3600):
        raise ApiError(429, "rate_limited", "Bạn đã gửi nhiều tin trong giờ qua, hãy thử lại sau")
    if body.topic not in TOPICS:
        raise ApiError(422, "invalid_topic", "Hãy chọn chủ đề")
    email = body.email.strip()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "invalid_email", "Email không hợp lệ")
    if len(re.findall(r"https?://", body.message)) > 3:
        raise ApiError(422, "too_many_links", "Tin nhắn có quá nhiều đường dẫn")
    u = await current_user(request)
    async with request.app.state.pool.connection() as conn:
        row = await (await conn.execute(
            """INSERT INTO contact_messages (name, email, phone, topic, message, page, user_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (body.name.strip(), email.lower(), body.phone.strip(), body.topic, body.message.strip(), body.page.strip(),
             u["id"] if u else None))).fetchone()
    try:
        await send_alert(request.app.state.settings, request.app.state.collector.http,
                         f"Liên hệ mới #{row['id']} ({TOPICS[body.topic]}) từ {body.name.strip()} <{email}>: {body.message.strip()[:200]}", level="info")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": row["id"]}
