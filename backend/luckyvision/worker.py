"""Tiến trình worker: lập lịch, theo dõi trực tiếp, đối soát, bù dữ liệu, chuyển sự kiện, cảnh báo.

Chạy: python -m luckyvision.worker
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from .alerts import heartbeat, send
from .collector.context import Ctx, make_http
from .collector.live import collect_draws, flush_alerts, pending_draws, watch
from .collector.planner import plan_day
from .config import VN_TZ, WINDOWS, get_settings
from .db import make_pool, migrate
from .events import relay_loop
from .forecast.service import evaluate_pending, generate_upcoming
from .sources.registry import build

log = logging.getLogger("luckyvision.worker")


def today() -> date:
    return datetime.now(VN_TZ).date()


class Worker:
    def __init__(self):
        self.settings = get_settings()
        self.pool = make_pool(self.settings.database_url, max_size=10)
        self.redis = Redis.from_url(self.settings.redis_url)
        self.ctx = Ctx(self.settings, self.pool, make_http(self.settings))
        # Máy ngủ hoặc tiến trình bận vẫn chạy bù job lỡ giờ khi thức dậy (gộp nhiều lần lỡ thành một), thay vì bỏ qua.
        self.sched = AsyncIOScheduler(timezone=VN_TZ, job_defaults={"misfire_grace_time": 6 * 3600, "coalesce": True})
        self.stop = asyncio.Event()

    # ---- công việc ----
    async def plan(self, day: date | None = None) -> None:
        day = day or today()
        async with self.pool.connection() as conn:
            for d in (day, day + timedelta(days=1)):
                n = await plan_day(conn, d)
                if n:
                    log.info("Đã lập %d kỳ quay dự kiến cho %s", n, d)
        self.schedule_live(day)
        await self.forecasts()

    def schedule_live(self, day: date) -> None:
        now = datetime.now(VN_TZ)
        for region, w in WINDOWS.items():
            start = datetime.combine(day, w.live_start, VN_TZ)
            end = datetime.combine(day, w.live_end, VN_TZ)
            if end <= now:
                continue
            self.sched.add_job(watch, "date", run_date=max(start, now + timedelta(seconds=2)),
                               args=[self.ctx, region, day], id=f"live-{region}-{day}", replace_existing=True,
                               misfire_grace_time=600)

    async def reconcile(self, region: str) -> None:
        draws = await pending_draws(self.ctx, region=region, since=today() - timedelta(days=2))
        if draws:
            log.info("Đối soát %d kỳ %s chưa công bố", len(draws), region)
            await collect_draws(self.ctx, draws)

    async def catch_up(self) -> None:
        """Lấy bù kỳ đã quá giờ quay 40 phút mà chưa có kết quả (3 ngày gần nhất). Cần khi máy tắt/ngủ đúng lúc
        đối soát: các mốc cron đã lỡ quá misfire_grace_time sẽ bị bỏ, kỳ đó không bao giờ được lấy nếu không bù."""
        # Máy tắt cả ngày thì lịch quay ngày đó chưa từng được lập (plan chạy 15:55 và 00:05): lập lại trước khi bù.
        async with self.pool.connection() as conn:
            for i in range(3, -1, -1):
                await plan_day(conn, today() - timedelta(days=i))
        cutoff = datetime.now(VN_TZ) - timedelta(minutes=40)
        draws = [d for d in await pending_draws(self.ctx, since=today() - timedelta(days=3))
                 if d.get("scheduled_at") and d["scheduled_at"] <= cutoff]
        if draws:
            log.info("Lấy bù %d kỳ quá giờ chưa có kết quả: %s", len(draws), ", ".join(d["id"] for d in draws[:10]))
            await collect_draws(self.ctx, draws)

    async def backfill(self) -> None:
        start = today() - timedelta(days=30)
        async with self.pool.connection() as conn:
            d = start
            while d <= today():
                await plan_day(conn, d)
                d += timedelta(days=1)
        draws = await pending_draws(self.ctx, since=start)
        log.info("Bù dữ liệu: %d kỳ trong 30 ngày qua chưa công bố", len(draws))
        if draws:
            await collect_draws(self.ctx, draws)

    async def overdue(self) -> None:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                """UPDATE lottery_draws SET alert_level = CASE WHEN critical_at <= now() THEN 2 ELSE 1 END
                    WHERE current_version IS NULL AND warn_at <= now()
                      AND alert_level < CASE WHEN critical_at <= now() THEN 2 ELSE 1 END
                RETURNING id, alert_level""")
            rows = await cur.fetchall()
        for r in rows:
            lvl = "critical" if r["alert_level"] == 2 else "warn"
            await send(self.settings, self.ctx.http, f"{r['id']}: đã quá giờ nhưng chưa có kết quả công bố.", lvl)

    async def source_health(self) -> None:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT * FROM data_sources WHERE enabled AND legal_approved AND kind NOT IN ('fixture','manual')")
            sources = await cur.fetchall()
        for src in sources:
            adapter = build(src, self.settings)
            if not adapter:
                continue
            t0 = asyncio.get_running_loop().time()
            ok, err = True, None
            try:
                await adapter.health(self.ctx.http)
            except Exception as e:  # noqa: BLE001
                ok, err = False, str(e)[:300]
            ms = int((asyncio.get_running_loop().time() - t0) * 1000)
            async with self.pool.connection() as conn:
                await conn.execute("INSERT INTO source_health (source_code, ok, latency_ms, error) VALUES (%s, %s, %s, %s)",
                                   (src["code"], ok, ms, err))

    async def forecasts(self) -> None:
        try:
            await generate_upcoming(self.pool)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi tạo dự báo")

    async def evaluate(self) -> None:
        try:
            await evaluate_pending(self.pool)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi chấm dự báo")

    async def play_check(self) -> None:
        from .play_service import check_pending
        try:
            async with self.pool.connection() as conn:
                n = await check_pending(conn)
            if n:
                log.info("Đã dò %d vé chơi thử", n)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi dò vé chơi thử")

    async def feeds(self) -> None:
        from .collector.feed import in_hours, run_feed
        if not in_hours():
            return
        try:
            res = await run_feed(self.ctx)
            if any(n for n, _ in res.values()):
                log.info("Kết quả mới: %s", {k: v[0] for k, v in res.items() if v[0]})
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi đọc kết quả theo dòng")

    # ---- tin tức ----
    async def news_sweep(self) -> None:
        from .news.service import sweep
        try:
            n = await sweep(self.pool, today())
            if n:
                log.info("Quét tin tức: đã ghi/cập nhật %d bài", n)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi quét tin tức")

    async def news_weekly(self) -> None:
        from .news.service import write_weekly
        try:
            n = await write_weekly(self.pool, today())
            log.info("Đã viết %d bài thống kê tuần", n)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi viết bài thống kê tuần")

    async def news_feeds(self) -> None:
        from .collector.feed import in_hours
        from .news.service import run_feeds
        if not in_hours():
            return
        try:
            n = await run_feeds(self.ctx)
            if n:
                log.info("Tin từ RSS: %d mục", n)
        except Exception:  # noqa: BLE001
            log.exception("Lỗi khi đọc RSS tin tức")

    async def beat(self) -> None:
        await heartbeat(self.settings, self.ctx.http)
        await flush_alerts(self.ctx)

    # ---- khởi động ----
    async def run(self) -> None:
        await asyncio.to_thread(migrate, self.settings.database_url)
        await self.pool.open(wait=True)
        s = self.sched
        s.add_job(self.plan, "cron", hour=15, minute=55, id="plan")
        s.add_job(self.plan, "cron", hour=0, minute=5, id="plan-midnight")
        for region, w in WINDOWS.items():
            for i, t in enumerate(w.reconcile):
                s.add_job(self.reconcile, "cron", hour=t.hour, minute=t.minute, args=[region], id=f"reconcile-{region}-{i}")
        s.add_job(self.backfill, "cron", hour=3, minute=0, id="backfill")
        s.add_job(self.catch_up, "interval", minutes=20, id="catch-up",
                  next_run_time=datetime.now(VN_TZ) + timedelta(seconds=45))   # chạy ngay sau khi khởi động
        s.add_job(self.overdue, "interval", minutes=1, id="overdue")
        s.add_job(self.beat, "interval", minutes=1, id="heartbeat")
        s.add_job(self.forecasts, "interval", minutes=30, id="forecasts")
        s.add_job(self.feeds, "interval", minutes=1, id="feeds")
        s.add_job(self.evaluate, "interval", minutes=3, id="evaluate")
        s.add_job(self.play_check, "interval", minutes=5, id="play-check")
        s.add_job(self.source_health, "cron", hour="8-23", minute="*/15", id="source-health")
        s.add_job(self.news_sweep, "interval", minutes=10, id="news-sweep",
                  next_run_time=datetime.now(VN_TZ) + timedelta(seconds=60))
        s.add_job(self.news_weekly, "cron", day_of_week="mon", hour=7, minute=0, id="news-weekly")
        s.add_job(self.news_feeds, "interval", minutes=30, id="news-feeds")
        s.start()
        await self.plan()
        from .notify import on_events
        from .news import service as news

        async def after(rows):
            try:
                await on_events(self.pool, self.ctx.http, self.settings, rows)
            except Exception:  # noqa: BLE001
                log.exception("Lỗi khi gửi thông báo")
            try:
                await news.on_events(self.pool, rows)
            except Exception:  # noqa: BLE001
                log.exception("Lỗi khi viết tin tức")
        relay = asyncio.create_task(relay_loop(self.pool, self.redis, self.stop, on_rows=after))
        log.info("Worker đã chạy (APP_ENV=%s)", self.settings.app_env)
        await self.stop.wait()
        s.shutdown(wait=False)
        await relay
        await self.ctx.http.aclose()
        await self.redis.aclose()
        await self.pool.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    w = Worker()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, w.stop.set)
        except NotImplementedError:  # Windows chạy ngoài Docker
            pass
    loop.run_until_complete(w.run())


if __name__ == "__main__":
    main()
