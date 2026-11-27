"""Đăng nhập quản trị: /v1/auth/*.

Phiên lưu trong cookie httpOnly 'lv_session' (SameSite=Strict). Mọi yêu cầu thay đổi dữ liệu dùng
cookie phải kèm header 'X-LV-CSRF: 1' (trang web khác không gửi được header này).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from ..audit import audit
from ..auth import (LOCK_MINUTES, MAX_FAILED, SESSION_HOURS, hash_password, new_session_token, new_totp_secret,
                    password_problem, token_hash, totp_uri, verify_password, verify_totp)
from .errors import ApiError

from ..ai import RateLimiter

router = APIRouter(prefix="/v1/auth", tags=["auth"])
LOGIN_LIMIT = RateLimiter()


def client_ip(request: Request) -> str | None:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else None)


def cookie_secure(request: Request) -> bool:
    s = request.app.state.settings
    if s.cookie_secure is not None:
        return s.cookie_secure
    return (not s.is_dev) or request.url.scheme == "https"
COOKIE = "lv_session"
SAFE = {"GET", "HEAD", "OPTIONS"}
_DUMMY = hash_password("dummy-password-for-timing")


async def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    async with request.app.state.pool.connection() as conn:
        return await (await conn.execute(
            """SELECT u.*, s.token_hash FROM admin_sessions s JOIN admin_users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND NOT s.revoked AND s.expires_at > now() AND u.active""",
            (token_hash(token),))).fetchone()


def check_csrf(request: Request) -> None:
    if request.method not in SAFE and request.headers.get("x-lv-csrf") != "1":
        raise ApiError(403, "csrf", "Thiếu header X-LV-CSRF")


async def session_user(request: Request) -> dict:
    user = await current_user(request)
    if not user:
        raise ApiError(401, "unauthorized", "Cần đăng nhập")
    check_csrf(request)
    return user


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "role": u["role"],
            "totp_enabled": u["totp_enabled"], "must_change_password": u["must_change_pw"],
            "last_login_at": u["last_login_at"].isoformat() if u.get("last_login_at") else None}


class LoginIn(BaseModel):
    username: str
    password: str
    otp: str | None = None


@router.post("/login")
async def login(request: Request, response: Response, body: LoginIn):
    username = body.username.strip().lower()
    ip = client_ip(request)
    if not LOGIN_LIMIT.allow(f"login:{ip}", request.app.state.settings.login_attempts_per_ip, window=300):
        raise ApiError(429, "rate_limited", "Thử đăng nhập quá nhiều lần từ địa chỉ này, hãy đợi 5 phút",
                       headers={"Retry-After": "300"})
    async with request.app.state.pool.connection() as conn:
        u = await (await conn.execute("SELECT * FROM admin_users WHERE username = %s FOR UPDATE", (username,))).fetchone()
        if not u or not u["active"]:
            verify_password(body.password, _DUMMY)  # giữ thời gian phản hồi như nhau
            raise ApiError(401, "invalid_credentials", "Sai tên đăng nhập hoặc mật khẩu")
        now = datetime.now(timezone.utc)
        if u["locked_until"] and u["locked_until"] > now:
            mins = int((u["locked_until"] - now).total_seconds() // 60) + 1
            raise ApiError(423, "account_locked", f"Tài khoản đang bị khóa tạm, thử lại sau {mins} phút")

        async def fail(code: str, msg: str):
            n = u["failed_logins"] + 1
            locked = now + timedelta(minutes=LOCK_MINUTES) if n >= MAX_FAILED else None
            await conn.execute("UPDATE admin_users SET failed_logins = %s, locked_until = %s WHERE id = %s",
                               (0 if locked else n, locked, u["id"]))
            await audit(conn, f"user:{username}", "login_failed", "admin_users", str(u["id"]), None,
                        {"ip": ip, "reason": code, "locked": bool(locked)})
            await conn.commit()
            raise ApiError(401, code, msg + (f". Tài khoản bị khóa {LOCK_MINUTES} phút." if locked else ""))

        if not verify_password(body.password, u["password_hash"]):
            await fail("invalid_credentials", "Sai tên đăng nhập hoặc mật khẩu")
        if u["totp_enabled"]:
            if not body.otp:
                raise ApiError(401, "otp_required", "Nhập mã 6 số từ ứng dụng xác thực")
            step = verify_totp(u["totp_secret"], body.otp, after_step=u["totp_last_step"])
            if step is None:
                await fail("invalid_otp", "Mã xác thực không đúng hoặc đã được dùng")
            await conn.execute("UPDATE admin_users SET totp_last_step = %s WHERE id = %s", (step, u["id"]))
        token, th = new_session_token()
        await conn.execute(
            "INSERT INTO admin_sessions (token_hash, user_id, expires_at, ip, user_agent) VALUES (%s, %s, %s, %s, %s)",
            (th, u["id"], now + timedelta(hours=SESSION_HOURS), ip, (request.headers.get("user-agent") or "")[:300]))
        await conn.execute("UPDATE admin_users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = %s",
                           (u["id"],))
        await audit(conn, f"user:{username}", "login", "admin_users", str(u["id"]), None, {"ip": ip})
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="strict",
                        secure=cookie_secure(request), path="/")
    u["last_login_at"] = now
    return {"user": public_user(u)}


@router.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(session_user)):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE admin_sessions SET revoked = true WHERE token_hash = %s", (user["token_hash"],))
        await audit(conn, f"user:{user['username']}", "logout", "admin_users", str(user["id"]))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict", secure=cookie_secure(request))
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(session_user)):
    return {"user": public_user(user)}


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/password")
async def change_password(request: Request, body: PasswordIn, user: dict = Depends(session_user)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise ApiError(400, "invalid_credentials", "Mật khẩu hiện tại không đúng")
    problem = password_problem(body.new_password)
    if problem:
        raise ApiError(422, "weak_password", problem)
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE admin_users SET password_hash = %s, must_change_pw = false WHERE id = %s",
                           (hash_password(body.new_password), user["id"]))
        await conn.execute("UPDATE admin_sessions SET revoked = true WHERE user_id = %s AND token_hash <> %s",
                           (user["id"], user["token_hash"]))
        await audit(conn, f"user:{user['username']}", "change_password", "admin_users", str(user["id"]))
    return {"ok": True}


@router.post("/totp/setup")
async def totp_setup(request: Request, user: dict = Depends(session_user)):
    if user["totp_enabled"]:
        raise ApiError(409, "totp_already_enabled", "Xác thực hai lớp đã bật")
    secret = new_totp_secret()
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE admin_users SET totp_secret = %s WHERE id = %s", (secret, user["id"]))
    return {"secret": secret, "otpauth_uri": totp_uri(secret, user["username"])}


class OtpIn(BaseModel):
    otp: str
    password: str | None = None


@router.post("/totp/enable")
async def totp_enable(request: Request, body: OtpIn, user: dict = Depends(session_user)):
    step = verify_totp(user["totp_secret"], body.otp) if user["totp_secret"] else None
    if step is None:
        raise ApiError(400, "invalid_otp", "Mã xác thực không đúng")
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE admin_users SET totp_enabled = true, totp_last_step = %s WHERE id = %s", (step, user["id"]))
        await audit(conn, f"user:{user['username']}", "enable_totp", "admin_users", str(user["id"]))
    return {"ok": True}


@router.post("/totp/disable")
async def totp_disable(request: Request, body: OtpIn, user: dict = Depends(session_user)):
    if not user["totp_enabled"]:
        raise ApiError(409, "totp_not_enabled", "Xác thực hai lớp chưa bật")
    if not body.password or not verify_password(body.password, user["password_hash"]) \
            or verify_totp(user["totp_secret"], body.otp, after_step=user["totp_last_step"]) is None:
        raise ApiError(400, "invalid_credentials", "Mật khẩu hoặc mã xác thực không đúng")
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE admin_users SET totp_enabled = false, totp_secret = NULL WHERE id = %s", (user["id"],))
        await audit(conn, f"user:{user['username']}", "disable_totp", "admin_users", str(user["id"]))
    return {"ok": True}
