"""Tự kiểm tra cấu hình, dữ liệu và bảo mật: python -m xs247.cli doctor"""
from __future__ import annotations

from importlib import resources
from urllib.parse import urlsplit

from redis.asyncio import Redis

from .config import Settings

OK, WARN, BAD = "OK ", "!! ", "XX "


async def run_checks(ctx) -> list[tuple[str, str, str]]:
    s: Settings = ctx.settings
    out: list[tuple[str, str, str]] = []
    add = lambda lvl, area, msg: out.append((lvl, area, msg))  # noqa: E731

    async with ctx.pool.connection() as conn:
        files = {p.name for p in resources.files("xs247.migrations").iterdir() if p.name.endswith(".sql")}
        done = {r["name"] for r in await (await conn.execute("SELECT name FROM schema_migrations")).fetchall()}
        missing = sorted(files - done)
        add(BAD if missing else OK, "Cơ sở dữ liệu", f"Thiếu migration: {', '.join(missing)}" if missing else f"Đã áp dụng đủ {len(done)} migration")

        try:
            r = Redis.from_url(s.redis_url)
            await r.ping()
            await r.aclose()
            add(OK, "Redis", "Kết nối được")
        except Exception as e:  # noqa: BLE001
            add(BAD, "Redis", f"Không kết nối được: {e}")

        # Cấu hình chung
        add(WARN if s.is_dev else OK, "Chế độ", "APP_ENV=dev: nguồn dữ liệu mẫu đang được dùng" if s.is_dev else "APP_ENV=prod")
        pw = urlsplit(s.database_url).password or ""
        if pw in ("luckey", "doi-mat-khau-nay") or len(pw) < 12:
            add(WARN, "Bảo mật", "Mật khẩu cơ sở dữ liệu yếu hoặc là giá trị mẫu; đặt POSTGRES_PASSWORD dài, ngẫu nhiên")
        else:
            add(OK, "Bảo mật", "Mật khẩu cơ sở dữ liệu đủ dài")
        tokens = s.admin_token_map()
        raw = [t for t in s.admin_tokens.split(",") if t.strip()]
        if len(raw) > len(tokens):
            add(WARN, "Bảo mật", f"{len(raw) - len(tokens)} token trong ADMIN_TOKENS bị bỏ qua (quá ngắn hoặc là giá trị mẫu)")
        if tokens:
            add(WARN, "Bảo mật", f"Có {len(tokens)} token dịch vụ đang hoạt động; token bỏ qua xác thực hai lớp, chỉ dùng cho script")
        if s.cookie_secure is False:
            add(BAD, "Bảo mật", "COOKIE_SECURE=false: cookie đăng nhập có thể bị gửi qua HTTP")
        elif s.is_dev and s.cookie_secure is None:
            add(WARN, "Bảo mật", "Chế độ dev: cookie đăng nhập chỉ bật Secure khi truy cập qua HTTPS")
        else:
            add(OK, "Bảo mật", "Cookie đăng nhập chỉ gửi qua HTTPS")

        # Tài khoản
        users = await (await conn.execute("SELECT * FROM admin_users WHERE active")).fetchall()
        admins = [u for u in users if u["role"] == "admin"]
        if not admins:
            add(BAD, "Tài khoản", "Chưa có tài khoản admin nào; chạy lệnh create-admin")
        else:
            no2fa = [u["username"] for u in users if not u["totp_enabled"] and u["role"] in ("admin", "editor")]
            add(WARN if no2fa else OK, "Tài khoản",
                f"Chưa bật xác thực hai lớp: {', '.join(no2fa)}" if no2fa else f"{len(users)} tài khoản, tất cả admin/editor đã bật hai lớp")
            pending = [u["username"] for u in users if u["must_change_pw"]]
            if pending:
                add(WARN, "Tài khoản", f"Còn dùng mật khẩu tạm: {', '.join(pending)}")

        # Nguồn dữ liệu
        srcs = await (await conn.execute("SELECT * FROM data_sources ORDER BY priority")).fetchall()
        bad = [x["code"] for x in srcs if x["enabled"] and not x["legal_approved"]]
        if bad:
            add(BAD, "Nguồn", f"Nguồn đang bật nhưng chưa duyệt pháp lý: {', '.join(bad)}")
        real = [x["code"] for x in srcs if x["enabled"] and x["legal_approved"] and x["kind"] not in ("fixture", "manual")]
        add(OK if real else WARN, "Nguồn", f"Đang bật: {', '.join(real)}" if real else "Chưa bật nguồn thật nào: kết quả mới không tự cập nhật")

        # Dữ liệu
        rows = await (await conn.execute(
            """SELECT region_code, max(draw_date) AS last FROM lottery_draws WHERE current_version IS NOT NULL
                GROUP BY region_code ORDER BY region_code""")).fetchall()
        add(OK if rows else WARN, "Dữ liệu", ", ".join(f"{r['region_code']}: {r['last']}" for r in rows) or "Chưa có kết quả nào")
        overdue = (await (await conn.execute(
            """SELECT count(*) AS n FROM lottery_draws WHERE current_version IS NULL AND warn_at < now()
                 AND draw_date >= current_date - 3""")).fetchone())["n"]
        add(WARN if overdue else OK, "Dữ liệu", f"{overdue} kỳ quá giờ chưa có kết quả trong 3 ngày qua" if overdue else "Không có kỳ quá giờ")
        backlog = (await (await conn.execute("SELECT count(*) AS n FROM outbox_events WHERE published_at IS NULL")).fetchone())["n"]
        add(WARN if backlog > 50 else OK, "Worker", f"{backlog} sự kiện chưa gửi (worker có thể đang dừng)" if backlog > 50 else "Hàng đợi sự kiện bình thường")
        fc = (await (await conn.execute(
            """SELECT count(*) AS n FROM forecasts f JOIN lottery_draws d ON d.id = f.draw_id
                WHERE d.current_version IS NULL AND d.scheduled_at > now()""")).fetchone())["n"]
        ev = (await (await conn.execute("SELECT count(*) AS n FROM forecast_evaluations")).fetchone())["n"]
        add(OK if fc else WARN, "Dự báo", f"{fc} dự báo cho các kỳ sắp quay, {ev} dự báo đã chấm" if fc else
            "Chưa có dự báo cho kỳ sắp quay (thiếu lịch sử hoặc worker chưa chạy)")

    add(OK if s.ai_enabled else WARN, "AI",
        f"Đã bật: {s.ai_provider}, mô hình {s.ai_model_name}" if s.ai_enabled else "Chưa đặt AI_API_KEY: trợ lý AI và AI chọn số đang tắt")
    if s.healthchecks_url or s.telegram_bot_token or s.slack_webhook_url:
        add(OK, "Cảnh báo", "Đã cấu hình kênh cảnh báo")
    else:
        add(WARN, "Cảnh báo", "Chưa cấu hình Telegram, Slack hay healthchecks: sẽ không biết khi hệ thống lỗi")
    return out
