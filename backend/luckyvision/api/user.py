"""Tài khoản người dùng công khai: /v1/user/*.

Phiên đăng nhập lưu trong cookie httpOnly 'lv_user' (SameSite=Lax, 30 ngày). Mọi yêu cầu thay đổi dữ liệu
phải kèm header 'X-LV-CSRF: 1'. Mật khẩu băm scrypt; khóa tạm sau nhiều lần sai; giới hạn số lần thử theo IP.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..ai import RateLimiter
from ..auth import hash_password, new_session_token, token_hash, verify_password
from ..domain.games import GAMES
from .auth import client_ip, cookie_secure
from .errors import ApiError

router = APIRouter(prefix="/v1/user", tags=["user"])
COOKIE = "lv_user"
DAYS = 30
LIMIT = RateLimiter()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,}$")
_DUMMY = hash_password("dummy-password-for-timing")
MAX_PROVINCES, MAX_SETS = 40, 60


def _check_csrf(request: Request) -> None:
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-lv-csrf") != "1":
        raise ApiError(403, "csrf", "Thiếu header X-LV-CSRF")


async def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    async with request.app.state.pool.connection() as conn:
        return await (await conn.execute(
            """SELECT u.*, s.token_hash FROM user_sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND NOT s.revoked AND s.expires_at > now() AND NOT u.disabled""", (token_hash(token),))).fetchone()


async def need_user(request: Request) -> dict:
    u = await current_user(request)
    if not u:
        raise ApiError(401, "unauthorized", "Cần đăng nhập")
    _check_csrf(request)
    return u


def _password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Mật khẩu cần ít nhất 8 ký tự"
    if pw.isdigit() or pw.isalpha():
        return "Mật khẩu cần có cả chữ và số"
    return None


async def _start_session(request: Request, response: Response, conn, user_id: int) -> None:
    token, th = new_session_token()
    await conn.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                       (th, user_id, datetime.now(timezone.utc) + timedelta(days=DAYS)))
    response.set_cookie(COOKIE, token, max_age=DAYS * 86400, httponly=True, samesite="lax",
                        secure=cookie_secure(request), path="/")


def _public(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "display_name": u["display_name"], "must_change_password": bool(u.get("must_change_pw")),
            "created_at": u["created_at"].isoformat() if u.get("created_at") else None}


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    display_name: str = Field(min_length=1, max_length=60)


@router.post("/register", status_code=201)
async def register(request: Request, response: Response, body: RegisterIn):
    _check_csrf(request)
    if not LIMIT.allow(f"reg:{client_ip(request)}", 5, window=3600):
        raise ApiError(429, "rate_limited", "Đăng ký quá nhiều lần từ địa chỉ này, hãy thử lại sau")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "invalid_email", "Email không hợp lệ")
    problem = _password_problem(body.password)
    if problem:
        raise ApiError(422, "weak_password", problem)
    async with request.app.state.pool.connection() as conn:
        if await (await conn.execute("SELECT 1 FROM users WHERE email = %s", (email,))).fetchone():
            raise ApiError(409, "email_taken", "Email này đã có tài khoản; hãy đăng nhập")
        u = await (await conn.execute(
            "INSERT INTO users (email, display_name, password_hash, last_login_at) VALUES (%s, %s, %s, now()) RETURNING *",
            (email, body.display_name.strip(), hash_password(body.password)))).fetchone()
        await _start_session(request, response, conn, u["id"])
    return {"user": _public(u)}


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/login")
async def login(request: Request, response: Response, body: LoginIn):
    _check_csrf(request)
    if not LIMIT.allow(f"ulogin:{client_ip(request)}", 10, window=300):
        raise ApiError(429, "rate_limited", "Thử đăng nhập quá nhiều lần, hãy đợi 5 phút")
    email = body.email.strip().lower()
    async with request.app.state.pool.connection() as conn:
        u = await (await conn.execute("SELECT * FROM users WHERE email = %s FOR UPDATE", (email,))).fetchone()
        now = datetime.now(timezone.utc)
        if not u:
            verify_password(body.password, _DUMMY)
            raise ApiError(401, "invalid_credentials", "Sai email hoặc mật khẩu")
        if u["disabled"]:
            raise ApiError(403, "account_disabled", "Tài khoản đang bị khóa. Hãy liên hệ quản trị.")
        if u["locked_until"] and u["locked_until"] > now:
            raise ApiError(423, "account_locked", "Tài khoản tạm khóa do sai mật khẩu nhiều lần, thử lại sau 15 phút")
        if not verify_password(body.password, u["password_hash"]):
            n = u["failed_logins"] + 1
            locked = now + timedelta(minutes=15) if n >= 8 else None
            await conn.execute("UPDATE users SET failed_logins = %s, locked_until = %s WHERE id = %s", (0 if locked else n, locked, u["id"]))
            await conn.commit()
            raise ApiError(401, "invalid_credentials", "Sai email hoặc mật khẩu")
        await conn.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = %s", (u["id"],))
        await _start_session(request, response, conn, u["id"])
    return {"user": _public(u)}


@router.post("/logout")
async def logout(request: Request, response: Response, u: dict = Depends(need_user)):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE user_sessions SET revoked = true WHERE token_hash = %s", (u["token_hash"],))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=cookie_secure(request))
    return {"ok": True}


@router.get("/me")
async def me(request: Request, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    u = await current_user(request)
    if not u:
        return {"user": None}
    async with request.app.state.pool.connection() as conn:
        provs = await (await conn.execute(
            """SELECT f.province_code AS code, p.name, p.region_code AS region FROM user_fav_provinces f
                 JOIN provinces p ON p.code = f.province_code WHERE f.user_id = %s ORDER BY f.created_at""", (u["id"],))).fetchall()
        sets = await (await conn.execute(
            "SELECT id, kind, scope, numbers, label FROM user_fav_sets WHERE user_id = %s ORDER BY created_at", (u["id"],))).fetchall()
    return {"user": _public(u), "favorites": {"provinces": provs, "sets": sets}}


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/password")
async def change_password(request: Request, body: PasswordIn, u: dict = Depends(need_user)):
    if not verify_password(body.current_password, u["password_hash"]):
        raise ApiError(400, "invalid_credentials", "Mật khẩu hiện tại không đúng")
    problem = _password_problem(body.new_password)
    if problem:
        raise ApiError(422, "weak_password", problem)
    async with request.app.state.pool.connection() as conn:
        await conn.execute("UPDATE users SET password_hash = %s, must_change_pw = false WHERE id = %s", (hash_password(body.new_password), u["id"]))
        await conn.execute("UPDATE user_sessions SET revoked = true WHERE user_id = %s AND token_hash <> %s", (u["id"], u["token_hash"]))
    return {"ok": True}


class DeleteIn(BaseModel):
    password: str


@router.post("/delete")
async def delete_account(request: Request, response: Response, body: DeleteIn, u: dict = Depends(need_user)):
    if not verify_password(body.password, u["password_hash"]):
        raise ApiError(400, "invalid_credentials", "Mật khẩu không đúng")
    async with request.app.state.pool.connection() as conn:
        await conn.execute("DELETE FROM users WHERE id = %s", (u["id"],))  # xóa kèm phiên, tỉnh và bộ số yêu thích
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ---------------- Yêu thích ----------------
@router.put("/favorites/provinces/{code}")
async def add_province(request: Request, code: str, u: dict = Depends(need_user)):
    async with request.app.state.pool.connection() as conn:
        p = await (await conn.execute("SELECT code FROM provinces WHERE code = %s AND active", (code,))).fetchone()
        if not p:
            raise ApiError(404, "province_not_found", "Không có đài này")
        n = (await (await conn.execute("SELECT count(*) AS n FROM user_fav_provinces WHERE user_id = %s", (u["id"],))).fetchone())["n"]
        if n >= MAX_PROVINCES:
            raise ApiError(400, "limit", f"Tối đa {MAX_PROVINCES} đài yêu thích")
        await conn.execute("INSERT INTO user_fav_provinces (user_id, province_code) VALUES (%s, %s) ON CONFLICT DO NOTHING", (u["id"], code))
    return {"ok": True}


@router.delete("/favorites/provinces/{code}")
async def remove_province(request: Request, code: str, u: dict = Depends(need_user)):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("DELETE FROM user_fav_provinces WHERE user_id = %s AND province_code = %s", (u["id"], code))
    return {"ok": True}


class SetIn(BaseModel):
    kind: str = Field(pattern=r"^(lo|pick|ticket)$")
    scope: str = Field(max_length=40)
    numbers: list[str] = Field(min_length=1, max_length=20)
    label: str = Field("", max_length=60)


def clean_set(body: SetIn) -> list[str]:
    nums = [re.sub(r"\D", "", n) for n in body.numbers]
    nums = [n for n in nums if n]
    if body.kind == "lo":
        if body.scope not in ("mb", "mn", "mt") and not re.match(r"^[a-z0-9-]{2,30}$", body.scope):
            raise ApiError(422, "invalid_scope", "Phạm vi không hợp lệ")
        out = sorted({n.zfill(2)[-2:] for n in nums if len(n) <= 2})
        if not out or len(out) > 10:
            raise ApiError(422, "invalid_numbers", "Bộ số lô gồm 1–10 số từ 00 đến 99")
        return out
    if body.kind == "pick":
        g = GAMES.get(body.scope)
        if not g or g.kind != "pick" or g.code in ("keno",):
            raise ApiError(422, "invalid_scope", "Chọn Power 6/55, Mega 6/45, Lotto 5/35 hoặc 6x36")
        vals = sorted({int(n) for n in nums})
        if len(vals) != g.main_count or not all(1 <= v <= g.main_max for v in vals):
            raise ApiError(422, "invalid_numbers", f"Bộ số {g.name} gồm {g.main_count} số khác nhau từ 01 đến {g.main_max:02d}")
        return [f"{v:02d}" for v in vals]
    # ticket
    if body.scope not in ("mb", "mn", "mt") and not re.match(r"^[a-z0-9-]{2,30}$", body.scope):
        raise ApiError(422, "invalid_scope", "Phạm vi không hợp lệ")
    need = 5 if body.scope == "mb" else 6
    out = [n for n in nums if len(n) == need]
    if not out or len(out) != len(nums):
        raise ApiError(422, "invalid_numbers", f"Số vé {'miền Bắc có 5' if need == 5 else 'miền Nam, miền Trung có 6'} chữ số")
    return out[:10]


@router.post("/favorites/sets", status_code=201)
async def add_set(request: Request, body: SetIn, u: dict = Depends(need_user)):
    nums = clean_set(body)
    async with request.app.state.pool.connection() as conn:
        n = (await (await conn.execute("SELECT count(*) AS n FROM user_fav_sets WHERE user_id = %s", (u["id"],))).fetchone())["n"]
        if n >= MAX_SETS:
            raise ApiError(400, "limit", f"Tối đa {MAX_SETS} bộ số")
        row = await (await conn.execute(
            "INSERT INTO user_fav_sets (user_id, kind, scope, numbers, label) VALUES (%s, %s, %s, %s, %s) RETURNING id, kind, scope, numbers, label",
            (u["id"], body.kind, body.scope, nums, body.label.strip()))).fetchone()
    return {"set": row}


@router.delete("/favorites/sets/{set_id}")
async def remove_set(request: Request, set_id: int, u: dict = Depends(need_user)):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("DELETE FROM user_fav_sets WHERE id = %s AND user_id = %s", (set_id, u["id"]))
    return {"ok": True}


@router.get("/dashboard")
async def dashboard(request: Request, response: Response, u: dict = Depends(need_user)):
    from ..site.personal import dashboard as build
    response.headers["Cache-Control"] = "private, no-store"
    async with request.app.state.pool.connection() as conn:
        return await build(conn, u["id"])
