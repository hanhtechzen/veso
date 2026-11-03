"""Lệnh quản trị: python -m luckyvision.cli <lệnh>

  migrate                         Tạo/cập nhật bảng
  plan --date 2026-10-29          Lập kỳ quay dự kiến của một ngày
  collect --draw ID | --date D    Chạy một lượt tải từ các nguồn đang bật
  simulate-live --draw ID         Giả lập buổi quay trực tiếp từ tệp mẫu (để thử SSE)
  sources                         Liệt kê nguồn dữ liệu và trạng thái
  probe-source CODE --draw ID     Thử tải và đọc một kỳ từ một nguồn, KHÔNG lưu gì (để kiểm tra bộ cào)
  source-enable CODE              Duyệt và bật một nguồn (ghi nhật ký)
  source-disable CODE             Tắt một nguồn
  create-admin --username U --name "Tên" [--role admin] [--password P]
                                  Tạo tài khoản quản trị (không có --password: tạo mật khẩu tạm, bắt đổi khi đăng nhập)
  backfill --region mn --days 120 Tải bù kết quả các ngày đã qua từ các nguồn đang bật
  forecast                        Tạo dự báo cho các kỳ sắp quay và chấm các dự báo đã có kết quả
  doctor                          Tự kiểm tra cấu hình, dữ liệu và bảo mật
  feed [--game keno] [--pages 1]  Đọc kết quả theo dòng (Keno, Bingo18, Lotto 5/35, Max 3D); nhiều trang để tải bù
  probe-feed GAME                 Thử đọc một trang kết quả của trò chơi, KHÔNG lưu gì
  backtest --region mb [--province mb] [--last 365] [--k 10]
                                  Kiểm thử lùi các mô hình trên dữ liệu trong cơ sở dữ liệu
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from redis.asyncio import Redis

from .collector.context import Ctx, make_http
from .collector.live import collect_draws, flush_alerts, pending_draws
from .collector.pipeline import get_draw, ingest
from .collector.planner import plan_day
from .config import get_settings
from .db import load_structure, make_pool, migrate
from .events import relay_once


async def _with_ctx(fn):
    s = get_settings()
    pool = make_pool(s.database_url, max_size=5)
    await pool.open(wait=True)
    ctx = Ctx(s, pool, make_http(s))
    try:
        return await fn(ctx)
    finally:
        await ctx.http.aclose()
        await pool.close()


async def cmd_plan(day: date) -> None:
    async def run(ctx):
        async with ctx.pool.connection() as conn:
            n = await plan_day(conn, day)
        print(f"Đã lập {n} kỳ quay dự kiến cho {day}")
    await _with_ctx(run)


async def cmd_collect(draw: str | None, day: date | None) -> None:
    async def run(ctx):
        if day:
            async with ctx.pool.connection() as conn:
                await plan_day(conn, day)
        draws = await pending_draws(ctx, day=day, draw_ids=[draw] if draw else None, include_published=bool(draw))
        print(f"Tải {len(draws)} kỳ quay...")
        await collect_draws(ctx, draws)
        async with ctx.pool.connection() as conn:
            for d in draws:
                row = await get_draw(conn, d["id"])
                print(f"  {row['id']}: {row['status']} (phiên bản {row['current_version']})")
    await _with_ctx(run)


async def cmd_simulate(draw_id: str, interval: float) -> None:
    async def run(ctx):
        s = ctx.settings
        f = Path(s.fixture_dir) / f"{draw_id}.json"
        full = json.loads(f.read_text(encoding="utf-8"))["prizes"]
        redis = Redis.from_url(s.redis_url)
        try:
            async with ctx.pool.connection() as conn:
                d = await get_draw(conn, draw_id)
                if not d:
                    print("Chưa có kỳ quay này. Chạy 'plan --date' trước."); return
                if d["current_version"] is not None:
                    print("Kỳ này đã công bố; giả lập vẫn phát số nhưng không tạo phiên bản mới.")
                structure = await load_structure(conn, d["region_code"], d["draw_date"])
            order = [p.code for p in structure.prizes]
            if "db" in order:  # giải đặc biệt quay cuối
                order = [c for c in order if c != "db"] + ["db"]
            partial: dict[str, list[str]] = {}
            for code in order:
                for n in full.get(code, []):
                    partial.setdefault(code, []).append(n)
                    async with ctx.pool.connection() as conn:
                        await ingest(conn, s, draw_id, "fixture-a", partial)
                    await relay_once(ctx.pool, redis)
                    print(f"  {code}: {n}")
                    await asyncio.sleep(interval)
            async with ctx.pool.connection() as conn:
                out = await ingest(conn, s, draw_id, "fixture-b", full)
            ctx.alerts.extend(out["alerts"])
            await relay_once(ctx.pool, redis)
            await flush_alerts(ctx)
            async with ctx.pool.connection() as conn:
                row = await get_draw(conn, draw_id)
            print(f"Xong: {draw_id} -> {row['status']} (phiên bản {row['current_version']})")
        finally:
            await redis.aclose()
    await _with_ctx(run)


async def cmd_sources() -> None:
    async def run(ctx):
        async with ctx.pool.connection() as conn:
            rows = await (await conn.execute("SELECT * FROM data_sources ORDER BY priority, code")).fetchall()
        print(f"{'Mã':<18}{'Loại':<12}{'Miền':<10}{'Duyệt':<8}{'Bật':<6}Tên")
        for r in rows:
            print(f"{r['code']:<18}{r['kind']:<12}{','.join(r['regions']) or 'tất cả':<10}"
                  f"{'có' if r['legal_approved'] else 'chưa':<8}{'có' if r['enabled'] else 'tắt':<6}{r['name']}")
    await _with_ctx(run)


async def cmd_probe(code: str, draw_id: str) -> None:
    from .collector.probe import probe

    async def run(ctx):
        r = await probe(ctx, code, draw_id)
        if r.get("url"):
            print(f"URL:        {r['url']}\nHTTP:       {r['http_status']}\nDung lượng: {r['bytes']} byte")
        if r.get("error"):
            print(("LỖI: " if "Lỗi" in r["error"] or "Không có" in r["error"] else "") + r["error"]); return
        for p in r["prizes"]:
            print(f"  {p['name']:<14}{' '.join(p['numbers']) or '(chưa có)'}")
        print("Đủ giải:    " + ("có" if r["complete"] else "chưa"))
        print("Kiểm tra:   " + ("hợp lệ" if not r["errors"] else "; ".join(r["errors"])))
        if r.get("meta"):
            print(f"Thông tin:  {r['meta']}")
    await _with_ctx(run)


async def cmd_source_toggle(code: str, enable: bool) -> None:
    from .audit import audit

    async def run(ctx):
        async with ctx.pool.connection() as conn:
            r = await (await conn.execute("SELECT * FROM data_sources WHERE code = %s FOR UPDATE", (code,))).fetchone()
            if not r:
                print(f"Không có nguồn {code}"); return
            if enable:
                await conn.execute("UPDATE data_sources SET legal_approved = true, enabled = true WHERE code = %s", (code,))
            else:
                await conn.execute("UPDATE data_sources SET enabled = false WHERE code = %s", (code,))
            await audit(conn, "cli", "enable_source" if enable else "disable_source", "data_sources", code,
                        {"legal_approved": r["legal_approved"], "enabled": r["enabled"]},
                        {"legal_approved": True if enable else r["legal_approved"], "enabled": enable})
        print(f"Đã {'bật' if enable else 'tắt'} nguồn {code}.")
    await _with_ctx(run)


async def cmd_create_admin(username: str, name: str, role: str, password: str | None) -> None:
    import secrets

    from .audit import audit
    from .auth import hash_password, password_problem

    must_change = password is None
    if password is None:
        password = secrets.token_urlsafe(9) + "A1"
    elif password_problem(password):
        print(password_problem(password)); return

    async def run(ctx):
        async with ctx.pool.connection() as conn:
            ex = await (await conn.execute("SELECT id FROM admin_users WHERE username = %s", (username,))).fetchone()
            if ex:
                await conn.execute("UPDATE admin_users SET password_hash = %s, must_change_pw = %s, role = %s, active = true, "
                                   "failed_logins = 0, locked_until = NULL, totp_enabled = false, totp_secret = NULL WHERE id = %s",
                                   (hash_password(password), must_change, role, ex["id"]))
                await audit(conn, "cli", "reset_user", "admin_users", str(ex["id"]), None, {"role": role})
                print(f"Đã đặt lại mật khẩu cho {username} và tắt xác thực hai lớp (bật lại trong Tài khoản của tôi).")
            else:
                r = await (await conn.execute(
                    "INSERT INTO admin_users (username, display_name, role, password_hash, must_change_pw) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id", (username, name, role, hash_password(password), must_change))).fetchone()
                await audit(conn, "cli", "create_user", "admin_users", str(r["id"]), None, {"username": username, "role": role})
                print(f"Đã tạo tài khoản {username} ({role}).")
        if must_change:
            print(f"Mật khẩu tạm: {password}\nĐăng nhập tại /admin.html, hệ thống sẽ yêu cầu đổi mật khẩu.")
    await _with_ctx(run)


async def cmd_backfill(region: str, days: int) -> None:
    from datetime import timedelta

    from .config import VN_TZ
    from datetime import datetime

    async def run(ctx):
        today = datetime.now(VN_TZ).date()
        start = today - timedelta(days=days)
        async with ctx.pool.connection() as conn:
            d = start
            while d <= today:
                await plan_day(conn, d)
                d += timedelta(days=1)
        draws = await pending_draws(ctx, region=region, since=start)
        print(f"{len(draws)} kỳ {region} chưa có kết quả từ {start}. Bắt đầu tải (tôn trọng giới hạn tần suất)...")
        for i in range(0, len(draws), 10):
            await collect_draws(ctx, draws[i:i + 10])
            print(f"  đã xử lý {min(i + 10, len(draws))}/{len(draws)}")
        left = await pending_draws(ctx, region=region, since=start)
        print(f"Xong. Còn {len(left)} kỳ chưa có kết quả (ngày nghỉ, nguồn chưa có, hoặc chờ quản trị duyệt).")
    await _with_ctx(run)


async def cmd_forecast() -> None:
    from .forecast.service import evaluate_pending, generate_upcoming

    async def run(ctx):
        made = await generate_upcoming(ctx.pool)
        done = await evaluate_pending(ctx.pool)
        print(f"Tạo {made} dự báo mới, chấm {done} dự báo.")
    await _with_ctx(run)


async def cmd_backtest(region: str, province: str | None, last: int, k: int | None) -> None:
    from datetime import date as _d

    from .forecast.service import K_VALUES, backtest, load_history

    from .domain.games import REGION_PROVINCE
    province = province or REGION_PROVINCE.get(region)
    if not province:
        print("Cần --province cho miền này (ví dụ --province tp-hcm)"); return

    async def run(ctx):
        async with ctx.pool.connection() as conn:
            days, draws, game = await load_history(conn, province, _d(9999, 1, 1))
        kk = k or (K_VALUES[game][0] if len(K_VALUES[game]) == 1 else 10)
        if kk not in K_VALUES[game]:
            print(f"k phải là một trong {K_VALUES[game]}"); return
        print(f"{province}: {len(draws)} kỳ trong cơ sở dữ liệu, kiểm thử {min(last, len(draws) - 1)} kỳ gần nhất, K = {kk}")
        res = backtest(draws, game, region, last, kk, province=province)
        print(f"{'Mô hình':<10}{'Số kỳ':>7}{'Precision':>11}{'Ngẫu nhiên':>12}{'Chênh lệch':>18}  Kết luận")
        verdict = {"better": "tốt hơn ngẫu nhiên", "worse": "kém hơn ngẫu nhiên", "no_difference": "không khác biệt",
                   "insufficient": "chưa đủ kỳ để kết luận"}
        for mid, r in res.items():
            if not r.get("n"):
                print(f"{mid:<10}  chưa đủ dữ liệu"); continue
            print(f"{mid:<10}{r['n']:>7}{r['precision']:>11.2%}{r['baseline_precision']:>12.2%}"
                  f"{r['diff'] * 100:>+10.2f} ±{r['ci95'] * 100:.2f} điểm %  {verdict[r['verdict']]}"
                  + (f"  Brier {r['brier']:.4f} / đều {r['brier_uniform']:.4f}" if r.get('brier') else ""))
    await _with_ctx(run)


async def cmd_doctor() -> int:
    from .doctor import BAD, WARN, run_checks

    async def run(ctx):
        rows = await run_checks(ctx)
        for lvl, area, msg in rows:
            print(f"{lvl} {area:<14}{msg}")
        bad = sum(1 for r in rows if r[0] == BAD)
        warn = sum(1 for r in rows if r[0] == WARN)
        print(f"\nKết quả: {bad} lỗi, {warn} cảnh báo. (OK = ổn, !! = nên xem lại, XX = cần sửa)")
        return 1 if bad else 0
    return await _with_ctx(run)


async def cmd_feed(game: str | None, pages: int) -> None:
    from .collector.feed import run_feed

    async def run(ctx):
        res = await run_feed(ctx, game, pages=pages, force=True)
        if not res:
            print("Không có nguồn theo dòng nào đang bật. Bật bằng: source-enable vietlott-keno (hoặc vietlott-lotto535...).")
        for g, (n, k) in res.items():
            print(f"{g}: {n} kỳ mới, {k} kỳ đã có")
    await _with_ctx(run)


async def cmd_probe_feed(game: str) -> None:
    from .sources.vietlott_feed import VietlottFeedAdapter

    async def run(ctx):
        ad = VietlottFeedAdapter(f"probe-{game}", {"game": game, "respect_robots": True}, ctx.settings)
        try:
            res, rows = await ad.fetch_page(ctx.http, 0)
        except Exception as e:  # noqa: BLE001
            print(f"LỖI: {type(e).__name__}: {e}"); return
        print(f"URL:  {res.url}\nHTTP: {res.status}\nĐọc được {len(rows)} kỳ")
        for r in rows[:5]:
            print(f"  {r.day:%d/%m/%Y} kỳ {r.seq}: " + "; ".join(f"{k}={' '.join(v)}" for k, v in r.prizes.items()))
    await _with_ctx(run)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="luckyvision")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sp = sub.add_parser("plan"); sp.add_argument("--date", required=True, type=date.fromisoformat)
    sc = sub.add_parser("collect"); sc.add_argument("--draw"); sc.add_argument("--date", type=date.fromisoformat)
    ss = sub.add_parser("simulate-live"); ss.add_argument("--draw", required=True); ss.add_argument("--interval", type=float, default=1.5)
    sub.add_parser("sources")
    sq = sub.add_parser("probe-source"); sq.add_argument("code"); sq.add_argument("--draw", required=True)
    se = sub.add_parser("source-enable"); se.add_argument("code")
    sd = sub.add_parser("source-disable"); sd.add_argument("code")
    sa = sub.add_parser("create-admin"); sa.add_argument("--username", required=True); sa.add_argument("--name", required=True)
    sa.add_argument("--role", default="admin", choices=["viewer", "editor", "admin"]); sa.add_argument("--password")
    sb = sub.add_parser("backfill"); sb.add_argument("--region", required=True, choices=["mb", "mn", "mt", "vl", "mega"])
    sb.add_argument("--days", type=int, default=60)
    sub.add_parser("forecast")
    sub.add_parser("doctor")
    sf = sub.add_parser("feed"); sf.add_argument("--game"); sf.add_argument("--pages", type=int, default=1)
    spf = sub.add_parser("probe-feed"); spf.add_argument("game", choices=["lotto535", "keno", "max3d", "max3dpro", "bingo18"])
    st = sub.add_parser("backtest"); st.add_argument("--region", required=True, choices=["mb", "mn", "mt", "vl", "mega"])
    st.add_argument("--province"); st.add_argument("--last", type=int, default=365); st.add_argument("--k", type=int)
    a = p.parse_args()
    if a.cmd == "migrate":
        applied = migrate(get_settings().database_url)
        print("Đã áp dụng: " + (", ".join(applied) if applied else "không có gì mới"))
    elif a.cmd == "plan":
        asyncio.run(cmd_plan(a.date))
    elif a.cmd == "collect":
        if not a.draw and not a.date:
            p.error("cần --draw hoặc --date")
        asyncio.run(cmd_collect(a.draw, a.date))
    elif a.cmd == "simulate-live":
        asyncio.run(cmd_simulate(a.draw, a.interval))
    elif a.cmd == "sources":
        asyncio.run(cmd_sources())
    elif a.cmd == "probe-source":
        asyncio.run(cmd_probe(a.code, a.draw))
    elif a.cmd == "create-admin":
        asyncio.run(cmd_create_admin(a.username.lower(), a.name, a.role, a.password))
    elif a.cmd == "backfill":
        asyncio.run(cmd_backfill(a.region, a.days))
    elif a.cmd == "feed":
        asyncio.run(cmd_feed(a.game, a.pages))
    elif a.cmd == "probe-feed":
        asyncio.run(cmd_probe_feed(a.game))
    elif a.cmd == "doctor":
        raise SystemExit(asyncio.run(cmd_doctor()))
    elif a.cmd == "forecast":
        asyncio.run(cmd_forecast())
    elif a.cmd == "backtest":
        asyncio.run(cmd_backtest(a.region, a.province, a.last, a.k))
    elif a.cmd in ("source-enable", "source-disable"):
        asyncio.run(cmd_source_toggle(a.code, a.cmd == "source-enable"))


if __name__ == "__main__":
    main()
