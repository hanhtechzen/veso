"""Dịch vụ tin tức: ghi bài tự sinh khi có kết quả công bố, quét bù, thống kê tuần và đọc RSS."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

from ..config import VN_TZ
from ..sources.html_util import ROBOTS
from ..site.data import _draws, day_draws, game_draws
from .articles import VIETLOTT_GAMES, region_day_article, vietlott_article, weekly_article
from .rss import fetch_feed

log = logging.getLogger("xs247.news")

ROUNDUP_REGIONS = ("mb", "mn", "mt")
VIETLOTT_REGIONS = {"vl": "power655", "mega": "mega645"}
EVENT_TYPES = ("draw.published", "draw.corrected")
_DATE_IN_ID = re.compile(r"(\d{4}-\d{2}-\d{2})")

_INSERT = """INSERT INTO news_articles (kind, topic, dedupe_key, slug, title, summary, body, region_code, draw_ids, ref_date,
                                      source_name, source_url, feed_code, published_at)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                     -- Bài kết quả mang giờ quay của kỳ (không phải giờ tạo bài, vì bài có thể được viết bù sau nhiều ngày)
                     least(now(), coalesce(%s, (SELECT max(scheduled_at) + interval '35 minutes' FROM lottery_draws
                                                WHERE id = ANY(%s::text[])), now())))"""
_ON_CONFLICT_AUTO = """ ON CONFLICT (dedupe_key) DO UPDATE SET title = EXCLUDED.title, summary = EXCLUDED.summary,
                          body = EXCLUDED.body, updated_at = now()
                          WHERE (news_articles.title, news_articles.summary, news_articles.body)
                                IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.summary, EXCLUDED.body)"""
_ON_CONFLICT_EXT = " ON CONFLICT (dedupe_key) DO NOTHING"


async def upsert_article(conn, art: dict) -> None:
    """Bài tự sinh: cập nhật tiêu đề/tóm tắt/nội dung khi có thay đổi (giữ published_at và hidden). Tin ngoài: bỏ qua nếu đã có."""
    body = art.get("body")
    sql = _INSERT + (_ON_CONFLICT_AUTO if art["kind"] == "auto" else _ON_CONFLICT_EXT)
    await conn.execute(sql, (art["kind"], art["topic"], art["dedupe_key"], art.get("slug"), art["title"], art.get("summary") or "",
                             Jsonb(body) if body is not None else None, art.get("region_code"), art.get("draw_ids"),
                             art.get("ref_date"), art.get("source_name"), art.get("source_url"), art.get("feed_code"),
                             art.get("published_at"), list(art.get("draw_ids") or [])))


async def region_day_complete(conn, region: str, day: date) -> bool:
    """Mọi kỳ của miền trong ngày đều đã công bố (và có ít nhất một kỳ)."""
    r = await (await conn.execute(
        """SELECT count(*) AS total, count(current_version) AS published FROM lottery_draws
            WHERE region_code = %s AND draw_date = %s""", (region, day))).fetchone()
    total, published = r["total"], r["published"]
    return bool(total) and total == published


async def write_region_day(conn, region: str, day: date) -> bool:
    if not await region_day_complete(conn, region, day):
        return False
    draws = await day_draws(conn, region, day)
    if not draws:
        return False
    await upsert_article(conn, region_day_article(region, day, draws))
    return True


async def write_vietlott(conn, game: str, draw: dict) -> None:
    if game in VIETLOTT_GAMES and draw.get("draw_seq") is not None:
        await upsert_article(conn, vietlott_article(game, draw))


async def on_events(pool, rows) -> None:
    """Móc vào relay sự kiện: kỳ vừa công bố/sửa -> viết (hoặc cập nhật) bài. Lỗi một sự kiện không chặn các sự kiện còn lại."""
    done: set[tuple] = set()
    async with pool.connection() as conn:
        for ev in rows:
            if (ev.get("type") or ev.get("topic")) not in EVENT_TYPES:   # hàng outbox thật dùng "topic", test dùng "type"
                continue
            p = ev.get("payload") or {}
            region, did = p.get("region") or ev.get("region_code"), p.get("draw_id") or ""
            try:
                if region in ROUNDUP_REGIONS:
                    m = _DATE_IN_ID.search(did)
                    key = (region, m[1] if m else None)
                    if not m or key in done:
                        continue
                    done.add(key)
                    await write_region_day(conn, region, date.fromisoformat(m[1]))
                elif region in VIETLOTT_REGIONS and did not in done:
                    done.add(did)
                    for d in await _draws(conn, "d.id = %s", (did,)):
                        await write_vietlott(conn, d.get("province_code") or p.get("province") or VIETLOTT_REGIONS[region], d)
            except Exception:  # noqa: BLE001
                log.exception("Không viết được bài tin tức cho sự kiện %s", did)


async def sweep(pool, today: date, days: int = 3) -> int:
    """Quét bù (idempotent): tổng hợp ngày đã đủ kỳ của mb/mn/mt và từng kỳ Vietlott đã công bố trong `days` ngày gần nhất."""
    n = 0
    since = today - timedelta(days=days - 1)
    async with pool.connection() as conn:
        for i in range(days):
            day = since + timedelta(days=i)
            for region in ROUNDUP_REGIONS:
                if await write_region_day(conn, region, day):
                    n += 1
        for game in VIETLOTT_GAMES:
            for d in await game_draws(conn, game, limit=20):
                if d["draw_date"] >= since:
                    await write_vietlott(conn, game, d)
                    n += 1
    return n


def previous_week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday() + 7)


async def write_weekly(pool, today: date) -> int:
    """Bài thống kê tuần trước (thứ Hai đến Chủ nhật) cho mb/mn/mt."""
    monday = previous_week_monday(today)
    n = 0
    async with pool.connection() as conn:
        for region in ROUNDUP_REGIONS:
            draws = await _draws(conn, "d.region_code = %s AND d.draw_date BETWEEN %s AND %s",
                                 (region, monday, monday + timedelta(days=6)), order="d.draw_date, p.name")
            if draws:
                await upsert_article(conn, weekly_article(region, monday, draws))
                n += 1
    return n


def _external(feed: dict, it: dict, now: datetime) -> dict | None:
    if urlsplit(it["url"]).scheme not in ("http", "https"):
        return None
    pub = it.get("published_at") or now
    return {"kind": "external", "topic": "external", "dedupe_key": "ext:" + hashlib.sha256(it["url"].encode()).hexdigest(),
            "slug": None, "title": it["title"], "summary": it["summary"], "body": None, "region_code": None, "draw_ids": None,
            "ref_date": None, "source_name": feed["name"], "source_url": it["url"], "feed_code": feed["code"],
            "published_at": min(pub, now)}


async def run_feeds(ctx, limit_per_feed: int = 30) -> int:
    """Đọc các nguồn RSS đã bật VÀ đã duyệt pháp lý, theo min_interval_s và robots.txt. Trả về số tin mới/gặp."""
    now = datetime.now(VN_TZ)
    async with ctx.pool.connection() as conn:
        feeds = await (await conn.execute("SELECT * FROM news_feeds WHERE enabled AND legal_approved ORDER BY code")).fetchall()
    total = 0
    for f in feeds:
        code = f["code"]
        last = f.get("last_fetched_at")
        if last and (now - last).total_seconds() < f["min_interval_s"]:
            continue
        if ctx.gate.is_open("news:" + code):
            continue
        denied: list[bool] = []

        async def allowed(url: str, _f=f) -> bool:
            ok = await ROBOTS.allowed(ctx.http, url, ctx.settings.user_agent)
            if not ok:
                denied.append(True)
            return ok
        err, items = None, []
        try:
            await ctx.gate.wait_turn("news:" + code, 1000)
            items = await fetch_feed(ctx.http, f, robots_allowed=allowed if f["respect_robots"] else None)
            if denied:
                err = "robots.txt không cho phép đọc nguồn này"
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300] or e.__class__.__name__
            log.warning("Đọc RSS %s lỗi: %s", code, err)
        async with ctx.pool.connection() as conn:
            if err:
                ctx.gate.failure("news:" + code)
                await conn.execute("UPDATE news_feeds SET last_fetched_at = now(), last_error = %s WHERE code = %s", (err, code))
                continue
            ctx.gate.success("news:" + code)
            for it in items[:limit_per_feed]:
                art = _external(f, it, now)
                if art:
                    await upsert_article(conn, art)
                    total += 1
            await conn.execute("UPDATE news_feeds SET last_fetched_at = now(), last_ok = now(), last_error = NULL WHERE code = %s",
                               (code,))
    return total
