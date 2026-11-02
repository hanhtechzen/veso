"""API quản trị (mục 6 tài liệu thiết kế). Đăng nhập bằng header Authorization: Bearer <token>.

Token cấu hình trong biến ADMIN_TOKENS="token:vai_trò:tên,...". Vai trò: viewer, editor, admin.
Ở bản chạy thật, đặt trang quản trị sau Cloudflare Access để thêm một lớp đăng nhập.
"""
from __future__ import annotations

import asyncio
import hmac
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from ..audit import audit
from ..collector.live import collect_draws, pending_draws
from ..collector.pipeline import get_draw, ingest, load_candidates, publish
from ..collector.planner import parse_draw_id
from ..config import VN_TZ, WINDOWS, get_settings
from ..db import load_structure
from ..domain.prizes import is_complete, normalize, ordered, validate
from ..domain.reconcile import diff
from .auth import check_csrf, current_user
from .errors import ApiError
from .serialize import iso

router = APIRouter(prefix="/v1/admin", tags=["admin"])
RANK = {"viewer": 0, "editor": 1, "admin": 2}


@dataclass
class Admin:
    name: str
    role: str
    username: str | None = None
    user_id: int | None = None

    @property
    def actor(self) -> str:
        return f"user:{self.username}" if self.username else f"token:{self.name}"


def require(role: str):
    """Chấp nhận phiên đăng nhập (cookie) hoặc token dịch vụ (header Authorization: Bearer ...)."""
    async def dep(request: Request, authorization: str | None = Header(None)) -> Admin:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            for t, (r, name) in get_settings().admin_token_map().items():
                if hmac.compare_digest(t, token):
                    if RANK.get(r, -1) < RANK[role]:
                        raise ApiError(403, "forbidden", f"Cần vai trò {role}")
                    return Admin(name, r)
            raise ApiError(401, "unauthorized", "Token không hợp lệ")
        user = await current_user(request)
        if not user:
            raise ApiError(401, "unauthorized", "Cần đăng nhập")
        check_csrf(request)
        if user["must_change_pw"]:
            raise ApiError(403, "must_change_password", "Cần đổi mật khẩu trước khi tiếp tục")
        if RANK.get(user["role"], -1) < RANK[role]:
            raise ApiError(403, "forbidden", f"Cần vai trò {role}")
        return Admin(user["display_name"], user["role"], user["username"], user["id"])
    return dep


def etag_of(d: dict) -> str:
    return f'"{d["current_version"] or 0}-{d["status"]}-{int(d["updated_at"].timestamp())}"'


@router.get("/review-queue")
async def review_queue(request: Request, _: Admin = Depends(require("viewer"))):
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT id, region_code, province_code, draw_date, status, current_version, scheduled_at, warn_at,
                      (current_version IS NULL AND warn_at < now()) AS overdue
                 FROM lottery_draws
                WHERE status IN ('needs_review', 'verified', 'validated') OR (current_version IS NULL AND warn_at < now())
                ORDER BY scheduled_at DESC LIMIT 200""")).fetchall()
    return {"items": [{"id": r["id"], "region": r["region_code"], "province": r["province_code"],
                       "draw_date": r["draw_date"].isoformat(), "status": r["status"], "version": r["current_version"],
                       "overdue": r["overdue"], "draw_time": iso(r["scheduled_at"])} for r in rows]}


@router.get("/draws/{draw_id}/candidates")
async def candidates(request: Request, draw_id: str, _: Admin = Depends(require("viewer"))):
    async with request.app.state.pool.connection() as conn:
        d = await get_draw(conn, draw_id)
        if not d:
            raise ApiError(404, "draw_not_found", "Không có kỳ quay này")
        cands = await load_candidates(conn, draw_id)
        rows = await (await conn.execute(
            "SELECT id, created_at, created_by FROM result_candidates WHERE draw_id = %s", (draw_id,))).fetchall()
    meta = {r["id"]: r for r in rows}
    latest = {}
    for c in cands:
        latest[c.source_code] = c
    items = sorted(latest.values(), key=lambda c: c.priority)
    base = items[0].payload if items else {}
    return {
        "draw": {"id": d["id"], "status": d["status"], "version": d["current_version"]},
        "etag": etag_of(d),
        "candidates": [{"id": c.id, "source": c.source_code, "complete": c.is_complete, "checksum": c.checksum,
                        "created_at": iso(meta[c.id]["created_at"]), "created_by": meta[c.id]["created_by"],
                        "prizes": c.payload, "differences_vs_first": diff(base, c.payload)} for c in items],
    }


class VerifyIn(BaseModel):
    candidate_id: int
    reason: str | None = None


@router.post("/draws/{draw_id}/verify")
async def verify(request: Request, draw_id: str, body: VerifyIn, who: Admin = Depends(require("admin"))):
    async with request.app.state.pool.connection() as conn:
        d = await get_draw(conn, draw_id, lock=True)
        if not d:
            raise ApiError(404, "draw_not_found", "Không có kỳ quay này")
        c = await (await conn.execute("SELECT payload, is_complete FROM result_candidates WHERE id = %s AND draw_id = %s",
                                      (body.candidate_id, draw_id))).fetchone()
        if not c:
            raise ApiError(404, "candidate_not_found", "Không có bản ứng viên này")
        structure = await load_structure(conn, d["region_code"], d["draw_date"])
        errs = validate(structure, c["payload"])
        if errs:
            raise ApiError(422, "validation_failed", "Bản ứng viên sai cơ cấu giải", errs)
        if d["current_version"] is not None and not body.reason:
            raise ApiError(400, "invalid_param", "Sửa kết quả đã công bố cần ghi lý do (reason)")
        version = await publish(conn, draw_id, body.candidate_id, who.actor, body.reason)
    return {"draw_id": draw_id, "version": version, "status": "published"}


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/draws/{draw_id}/needs-review")
async def needs_review(request: Request, draw_id: str, body: ReasonIn, who: Admin = Depends(require("editor"))):
    async with request.app.state.pool.connection() as conn:
        d = await get_draw(conn, draw_id, lock=True)
        if not d:
            raise ApiError(404, "draw_not_found", "Không có kỳ quay này")
        await conn.execute("UPDATE lottery_draws SET status = 'needs_review', updated_at = now() WHERE id = %s", (draw_id,))
        await audit(conn, who.actor, "needs_review", "lottery_draws", draw_id, {"status": d["status"]},
                    {"status": "needs_review", "reason": body.reason})
    return {"draw_id": draw_id, "status": "needs_review"}


class ResultsIn(BaseModel):
    prizes: dict[str, list[str]]
    reason: str | None = None


@router.put("/draws/{draw_id}/results")
async def put_results(request: Request, draw_id: str, body: ResultsIn, who: Admin = Depends(require("editor")),
                      if_match: str | None = Header(None)):
    """Nhập tay hoặc sửa kết quả. Tạo bản ứng viên nguồn 'manual', kỳ quay chuyển sang chờ xác minh."""
    async with request.app.state.pool.connection() as conn:
        d = await get_draw(conn, draw_id, lock=True)
        if not d:
            try:
                region, province, day = parse_draw_id(draw_id)
            except ValueError:
                raise ApiError(400, "invalid_param", "Mã kỳ quay phải có dạng <miền>-<đài>-<YYYY-MM-DD>")
            p = await (await conn.execute("SELECT region_code, game FROM provinces WHERE code = %s", (province,))).fetchone()
            if not p or p["region_code"] != region:
                raise ApiError(400, "invalid_param", "Không có đài này trong miền đã chọn")
            from datetime import datetime as _dt
            from datetime import time as _t
            w = WINDOWS.get(region)
            await conn.execute(
                """INSERT INTO lottery_draws (id, game, region_code, province_code, draw_date, scheduled_at, warn_at, critical_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (draw_id, p["game"], region, province, day, _dt.combine(day, w.live_start if w else _t(18, 0), VN_TZ),
                 _dt.combine(day, w.warn, VN_TZ) if w else None, _dt.combine(day, w.critical, VN_TZ) if w else None))
            d = await get_draw(conn, draw_id, lock=True)
        if if_match and if_match != etag_of(d):
            raise ApiError(409, "version_conflict", "Kỳ quay đã thay đổi, tải lại rồi thử lại")
        if d["current_version"] is not None and not body.reason:
            raise ApiError(400, "invalid_param", "Sửa kết quả đã công bố cần ghi lý do (reason)")
        structure = await load_structure(conn, d["region_code"], d["draw_date"])
        prizes = normalize(body.prizes)
        if structure.game == "power655":  # cho phép gõ 9 thay vì 09
            prizes = {k: [n.zfill(2) if n.isdigit() else n for n in v] for k, v in prizes.items()}
        prizes = ordered(structure, prizes)
        errs = validate(structure, prizes)
        if errs or not is_complete(structure, prizes):
            raise ApiError(422, "validation_failed", "Sai cơ cấu giải", errs)
        out = await ingest(conn, request.app.state.settings, draw_id, "manual", prizes, created_by=who.actor)
        await conn.execute("UPDATE lottery_draws SET status = 'needs_review', updated_at = now() WHERE id = %s", (draw_id,))
        await audit(conn, who.actor, "manual_entry", "lottery_draws", draw_id, None,
                    {"candidate_id": out["candidate_id"], "reason": body.reason, "prizes": prizes})
    return {"draw_id": draw_id, "candidate_id": out["candidate_id"], "status": "needs_review"}


class CollectIn(BaseModel):
    draw_id: str


@router.post("/collect", status_code=202)
async def collect(request: Request, body: CollectIn, who: Admin = Depends(require("editor"))):
    ctx = request.app.state.collector
    draws = await pending_draws(ctx, draw_ids=[body.draw_id], include_published=True)
    if not draws:
        raise ApiError(404, "draw_not_found", "Không có kỳ quay này hoặc chưa tới giờ quay")
    async with request.app.state.pool.connection() as conn:
        await audit(conn, who.actor, "collect", "lottery_draws", body.draw_id)
    asyncio.create_task(collect_draws(ctx, draws))
    return {"draw_id": body.draw_id, "queued": True}


SOURCE_FIELDS = ("code", "name", "kind", "adapter", "config", "regions", "legal_approved", "enabled", "rate_limit_ms", "priority")


@router.get("/sources")
async def sources(request: Request, _: Admin = Depends(require("viewer"))):
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute("SELECT * FROM data_sources ORDER BY priority, code")).fetchall()
    return {"items": [{k: r[k] for k in SOURCE_FIELDS} for r in rows]}


@router.get("/sources/{code}")
async def source(request: Request, code: str, _: Admin = Depends(require("viewer"))):
    async with request.app.state.pool.connection() as conn:
        r = await (await conn.execute("SELECT * FROM data_sources WHERE code = %s", (code,))).fetchone()
        if not r:
            raise ApiError(404, "source_not_found", "Không có nguồn này")
        h = await (await conn.execute(
            "SELECT checked_at, ok, latency_ms, error FROM source_health WHERE source_code = %s ORDER BY checked_at DESC LIMIT 20",
            (code,))).fetchall()
    return {**{k: r[k] for k in SOURCE_FIELDS}, "health": [{**x, "checked_at": iso(x["checked_at"])} for x in h]}


class SourcePatch(BaseModel):
    enabled: bool | None = None
    legal_approved: bool | None = None
    rate_limit_ms: int | None = Field(None, ge=0, le=600000)
    priority: int | None = None
    config: dict | None = None
    regions: list[str] | None = None


@router.patch("/sources/{code}")
async def patch_source(request: Request, code: str, body: SourcePatch, who: Admin = Depends(require("admin"))):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise ApiError(400, "invalid_param", "Không có thay đổi")
    async with request.app.state.pool.connection() as conn:
        r = await (await conn.execute("SELECT * FROM data_sources WHERE code = %s FOR UPDATE", (code,))).fetchone()
        if not r:
            raise ApiError(404, "source_not_found", "Không có nguồn này")
        legal = changes.get("legal_approved", r["legal_approved"])
        if changes.get("enabled", r["enabled"]) and not legal:
            raise ApiError(422, "validation_failed", "Chỉ bật được nguồn đã duyệt pháp lý (legal_approved = true)")
        sets, args = [], []
        for k, v in changes.items():
            sets.append(f"{k} = %s"); args.append(Jsonb(v) if k == "config" else v)
        await conn.execute(f"UPDATE data_sources SET {', '.join(sets)} WHERE code = %s", (*args, code))
        await audit(conn, who.actor, "update_source", "data_sources", code,
                    {k: r[k] for k in changes}, changes)
    return {"code": code, "updated": list(changes)}


@router.get("/audit-logs")
async def audit_logs(request: Request, entity: str | None = None, entity_id: str | None = None,
                     actor: str | None = None, limit: int = 100, _: Admin = Depends(require("viewer"))):
    q, args = ["SELECT * FROM audit_logs WHERE true"], []
    for col, v in (("entity", entity), ("entity_id", entity_id), ("actor", actor)):
        if v:
            q.append(f"AND {col} = %s"); args.append(v)
    q.append("ORDER BY id DESC LIMIT %s"); args.append(min(max(limit, 1), 500))
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(" ".join(q), args)).fetchall()
    return {"items": [{**r, "at": iso(r["at"])} for r in rows]}


# ===================== Quản lý tài khoản =====================
def _user_out(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "role": u["role"],
            "active": u["active"], "totp_enabled": u["totp_enabled"], "must_change_password": u["must_change_pw"],
            "locked": bool(u["locked_until"] and u["locked_until"].timestamp() > __import__("time").time()),
            "last_login_at": iso(u["last_login_at"]), "created_at": iso(u["created_at"])}


@router.get("/users")
async def list_users(request: Request, _: Admin = Depends(require("admin"))):
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute("SELECT * FROM admin_users ORDER BY id")).fetchall()
    return {"items": [_user_out(u) for u in rows]}


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,40}$")
    display_name: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern=r"^(viewer|editor|admin)$")


@router.post("/users", status_code=201)
async def create_user(request: Request, body: UserIn, who: Admin = Depends(require("admin"))):
    from ..auth import hash_password
    import secrets
    temp = secrets.token_urlsafe(9) + "A1"
    async with request.app.state.pool.connection() as conn:
        exists = await (await conn.execute("SELECT 1 FROM admin_users WHERE username = %s", (body.username,))).fetchone()
        if exists:
            raise ApiError(409, "duplicate_user", "Tên đăng nhập đã tồn tại")
        u = await (await conn.execute(
            """INSERT INTO admin_users (username, display_name, role, password_hash, must_change_pw)
               VALUES (%s, %s, %s, %s, true) RETURNING *""",
            (body.username, body.display_name, body.role, hash_password(temp)))).fetchone()
        await audit(conn, who.actor, "create_user", "admin_users", str(u["id"]), None,
                    {"username": body.username, "role": body.role})
    return {"user": _user_out(u), "temporary_password": temp}


class UserPatch(BaseModel):
    display_name: str | None = None
    role: str | None = Field(None, pattern=r"^(viewer|editor|admin)$")
    active: bool | None = None
    reset_password: bool = False
    reset_totp: bool = False


@router.patch("/users/{user_id}")
async def patch_user(request: Request, user_id: int, body: UserPatch, who: Admin = Depends(require("admin"))):
    from ..auth import hash_password
    import secrets
    if who.user_id == user_id and (body.active is False or (body.role and body.role != "admin")):
        raise ApiError(400, "invalid_param", "Không thể tự khóa hoặc tự hạ quyền tài khoản của mình")
    async with request.app.state.pool.connection() as conn:
        u = await (await conn.execute("SELECT * FROM admin_users WHERE id = %s FOR UPDATE", (user_id,))).fetchone()
        if not u:
            raise ApiError(404, "user_not_found", "Không có tài khoản này")
        sets, args, temp = [], [], None
        for k in ("display_name", "role", "active"):
            v = getattr(body, k)
            if v is not None:
                sets.append(f"{k} = %s"); args.append(v)
        if body.reset_password:
            temp = secrets.token_urlsafe(9) + "A1"
            sets += ["password_hash = %s", "must_change_pw = true", "failed_logins = 0", "locked_until = NULL"]
            args.append(hash_password(temp))
        if body.reset_totp:
            sets += ["totp_enabled = false", "totp_secret = NULL"]
        if not sets:
            raise ApiError(400, "invalid_param", "Không có thay đổi")
        u2 = await (await conn.execute(f"UPDATE admin_users SET {', '.join(sets)} WHERE id = %s RETURNING *",
                                       (*args, user_id))).fetchone()
        if body.active is False or body.reset_password:
            await conn.execute("UPDATE admin_sessions SET revoked = true WHERE user_id = %s", (user_id,))
        await audit(conn, who.actor, "update_user", "admin_users", str(user_id),
                    {"role": u["role"], "active": u["active"]},
                    {k: v for k, v in body.model_dump().items() if v not in (None, False)})
    out = {"user": _user_out(u2)}
    if temp:
        out["temporary_password"] = temp
    return out


@router.get("/sources/{code}/probe")
async def probe_source(request: Request, code: str, draw_id: str, _: Admin = Depends(require("admin"))):
    """Thử tải và đọc một kỳ từ nguồn, không lưu gì."""
    from ..collector.probe import probe
    return await probe(request.app.state.collector, code, draw_id)
