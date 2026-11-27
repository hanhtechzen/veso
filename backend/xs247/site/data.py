"""Truy vấn dữ liệu cho các trang công khai (đã công bố)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..domain.games import GAMES

REGION_NAMES = {"mb": "miền Bắc", "mn": "miền Nam", "mt": "miền Trung"}
REGION_SLUG = {"mb": "xsmb", "mn": "xsmn", "mt": "xsmt"}
SLUG_REGION = {v: k for k, v in REGION_SLUG.items()}
DISPLAY = {
    "mb": ["db", "g1", "g2", "g3", "g4", "g5", "g6", "g7"],
    "mn": ["g8", "g7", "g6", "g5", "g4", "g3", "g2", "g1", "db"],
    "mt": ["g8", "g7", "g6", "g5", "g4", "g3", "g2", "g1", "db"],
}
PRIZE_SHORT = {"db": "ĐB", **{f"g{i}": f"G{i}" for i in range(1, 9)}}
WEEKDAY = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def slug_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def parse_slug_date(s: str) -> date | None:
    try:
        dd, mm, yy = (int(x) for x in s.split("-"))
        return date(yy, mm, dd)
    except (ValueError, TypeError):
        return None


def weekday(d: date) -> str:
    return WEEKDAY[d.weekday()]


async def _draws(conn, where: str, args: tuple, limit: int | None = None, order: str = "d.draw_date DESC, p.name") -> list[dict]:
    """Các kỳ đã công bố kèm kết quả, gom theo kỳ."""
    sql = f"""SELECT d.id, d.region_code, d.province_code, d.draw_date, d.draw_seq, d.current_version, p.name AS pname, p.game
                FROM lottery_draws d JOIN provinces p ON p.code = d.province_code
               WHERE d.current_version IS NOT NULL AND {where} ORDER BY {order}""" + (f" LIMIT {int(limit)}" if limit else "")
    draws = await (await conn.execute(sql, args)).fetchall()
    if not draws:
        return []
    rows = await (await conn.execute(
        """SELECT r.draw_id, r.prize_code, r.position, r.number FROM lottery_results r
             JOIN lottery_draws d ON d.id = r.draw_id AND r.version = d.current_version
            WHERE r.draw_id = ANY(%s) ORDER BY r.draw_id, r.prize_code, r.position""", ([d["id"] for d in draws],))).fetchall()
    prizes: dict[str, dict[str, list[str]]] = {}
    for r in rows:
        prizes.setdefault(r["draw_id"], {}).setdefault(r["prize_code"], []).append(r["number"])
    out = []
    for d in draws:
        pr = prizes.get(d["id"], {})
        loto = sorted(int(n[-2:]) for v in pr.values() for n in v) if d["game"] == "xs" else []
        out.append({**d, "prizes": pr, "loto": loto})
    return out


async def latest_day(conn, region: str) -> date | None:
    r = await (await conn.execute(
        "SELECT max(draw_date) AS d FROM lottery_draws WHERE region_code = %s AND current_version IS NOT NULL", (region,))).fetchone()
    return r["d"]


async def neighbour_days(conn, region: str, day: date) -> tuple[date | None, date | None]:
    prev = await (await conn.execute(
        "SELECT max(draw_date) AS d FROM lottery_draws WHERE region_code = %s AND current_version IS NOT NULL AND draw_date < %s",
        (region, day))).fetchone()
    nxt = await (await conn.execute(
        "SELECT min(draw_date) AS d FROM lottery_draws WHERE region_code = %s AND current_version IS NOT NULL AND draw_date > %s",
        (region, day))).fetchone()
    return prev["d"], nxt["d"]


async def day_draws(conn, region: str, day: date) -> list[dict]:
    return await _draws(conn, "d.region_code = %s AND d.draw_date = %s", (region, day), order="p.name")


async def province(conn, code: str) -> dict | None:
    return await (await conn.execute("SELECT * FROM provinces WHERE code = %s AND active", (code,))).fetchone()


async def province_draws(conn, code: str, limit: int = 10) -> list[dict]:
    return await _draws(conn, "d.province_code = %s", (code,), limit=limit, order="d.draw_date DESC")


async def region_range(conn, region: str, days: int) -> list[dict]:
    last = await latest_day(conn, region)
    if not last:
        return []
    return await _draws(conn, "d.region_code = %s AND d.draw_date > %s", (region, last - timedelta(days=days)),
                        order="d.draw_date DESC, p.name")


async def game_draws(conn, game: str, limit: int = 20, day: date | None = None) -> list[dict]:
    if day:
        return await _draws(conn, "d.province_code = %s AND d.draw_date = %s", (game, day), order="d.draw_seq DESC NULLS LAST")
    return await _draws(conn, "d.province_code = %s", (game,), limit=limit, order="d.draw_date DESC, d.draw_seq DESC NULLS LAST")


async def next_draws(conn, now: datetime | None = None, games: list[str] | None = None, horizon: int = 8) -> dict[str, datetime]:
    """Giờ quay kế tiếp theo lịch (đã loại ngày nghỉ) của từng trò chơi Vietlott; dùng lại planner.day_slots.
    Trò chơi không có lịch trong draw_schedules (ví dụ Keno, Bingo18) sẽ không có trong kết quả."""
    from ..collector.planner import day_slots
    from ..config import VN_TZ
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    want = set(games or [g.code for g in GAMES.values() if g.family == "vietlott"])
    out: dict[str, datetime] = {}
    for i in range(horizon):
        day = now.date() + timedelta(days=i)
        for s in await day_slots(conn, day):
            code = s["province_code"]
            if code not in want:
                continue
            at = datetime.combine(day, s["draw_time"], VN_TZ)
            if at > now and (code not in out or at < out[code]):
                out[code] = at
        if want <= set(out):
            break
    return out


async def scheduled_count(conn, code: str, after: date, upto: date, limit: int = 120) -> int | None:
    """Số kỳ theo lịch (đã loại ngày nghỉ) của một trò chơi trong khoảng (after, upto]; None nếu khoảng quá dài.
    Dùng để tính số kỳ kế tiếp đúng cả khi dữ liệu đang thiếu vài kỳ gần nhất."""
    from ..collector.planner import day_slots
    if (upto - after).days > limit:
        return None
    n, day = 0, after + timedelta(days=1)
    while day <= upto:
        n += sum(1 for s in await day_slots(conn, day) if s["province_code"] == code)
        day += timedelta(days=1)
    return n


async def provinces_of(conn, region: str) -> list[dict]:
    return await (await conn.execute(
        """SELECT p.code, p.name, array_agg(DISTINCT s.iso_weekday ORDER BY s.iso_weekday) AS days
             FROM provinces p LEFT JOIN draw_schedules s ON s.province_code = p.code AND (s.valid_to IS NULL OR s.valid_to >= current_date)
            WHERE p.region_code = %s AND p.active GROUP BY p.code ORDER BY p.name""", (region,))).fetchall()


def gan_stats(draws_oldest_first: list[dict], top: int = 15) -> dict:
    """Lô gan (số kỳ liên tiếp chưa về) và tần suất 30 kỳ gần nhất."""
    last_seen: dict[int, int] = {}
    for i, d in enumerate(draws_oldest_first):
        for n in set(d["loto"]):
            last_seen[n] = i
    n_draws = len(draws_oldest_first)
    gan = sorted(((n, n_draws - 1 - last_seen.get(n, -1)) for n in range(100)), key=lambda x: (-x[1], x[0]))[:top]
    recent = draws_oldest_first[-30:]
    freq = {n: 0 for n in range(100)}
    for d in recent:
        for n in d["loto"]:
            freq[n] += 1
    hot = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:10]
    cold = sorted(freq.items(), key=lambda x: (x[1], x[0]))[:10]
    return {"gan": gan, "hot": hot, "cold": cold, "draws": n_draws, "recent": len(recent)}


def head_tail(lotos: list[str]) -> dict:
    """Đếm theo chữ số đầu và chữ số cuối của các lô 2 chữ số: {"dau": {0..9: n}, "duoi": {0..9: n}}."""
    dau = {i: 0 for i in range(10)}
    duoi = {i: 0 for i in range(10)}
    for n in lotos:
        dau[int(n[0])] += 1
        duoi[int(n[-1])] += 1
    return {"dau": dau, "duoi": duoi}


def snapshot_from_draws(region: str, draws: list[dict], top: int = 5) -> dict:
    """Thống kê nhanh của một miền từ các kỳ đã công bố (mọi đài). Đơn vị "gan" là số NGÀY quay của miền."""
    by_day: dict[date, list[int]] = {}
    for d in draws:
        by_day.setdefault(d["draw_date"], []).extend(d["loto"])
    days = sorted(by_day, reverse=True)           # mới nhất trước
    if not days:
        return {"region": region, "region_name": REGION_NAMES.get(region, region), "unit": "ngày", "as_of": None,
                "days": 0, "gan_top": [], "hot30": [], "head_tail": head_tail([])}
    gap: dict[int, int] = {}
    for i, day in enumerate(days):
        for n in set(by_day[day]):
            gap.setdefault(n, i)
    gan = sorted(((n, gap.get(n, len(days))) for n in range(100)), key=lambda x: (-x[1], x[0]))[:top]
    cut = days[0] - timedelta(days=30)
    freq = {n: 0 for n in range(100)}
    for day in days:
        if day > cut:
            for n in by_day[day]:
                freq[n] += 1
    hot = sorted(((n, c) for n, c in freq.items() if c), key=lambda x: (-x[1], x[0]))[:top]
    return {"region": region, "region_name": REGION_NAMES.get(region, region), "unit": "ngày", "as_of": days[0].isoformat(),
            "days": len(days), "gan_top": [{"number": f"{n:02d}", "days": g} for n, g in gan],
            "hot30": [{"number": f"{n:02d}", "count": c} for n, c in hot],
            "head_tail": head_tail([f"{n:02d}" for n in by_day[days[0]]])}


_SNAP_CACHE: dict[str, tuple[tuple, dict]] = {}


async def region_snapshot(conn, region: str) -> dict:
    """Thống kê nhanh của miền; lưu cache theo (số kỳ đã công bố, mốc công bố mới nhất) nên chỉ tính lại khi có kỳ mới/sửa."""
    mark = await (await conn.execute(
        "SELECT count(*) AS n, max(published_at) AS p FROM lottery_draws WHERE region_code = %s AND current_version IS NOT NULL",
        (region,))).fetchone()
    key = (mark["n"], mark["p"])
    hit = _SNAP_CACHE.get(region)
    if hit and hit[0] == key:
        return hit[1]
    snap = snapshot_from_draws(region, await region_range(conn, region, 365))
    _SNAP_CACHE[region] = (key, snap)
    return snap


async def sitemap_entries(conn) -> list[tuple[str, date | None]]:
    out: list[tuple[str, date | None]] = []
    for region, slug in REGION_SLUG.items():
        days = await (await conn.execute(
            """SELECT DISTINCT draw_date FROM lottery_draws WHERE region_code = %s AND current_version IS NOT NULL
                ORDER BY draw_date DESC""", (region,))).fetchall()
        if days:
            out.append((f"/{slug}", days[0]["draw_date"]))
            out.append((f"/thong-ke-{slug}", days[0]["draw_date"]))
            for n in (30, 60, 90):
                out.append((f"/so-ket-qua-{slug}-{n}-ngay", days[0]["draw_date"]))
        out += [(f"/{slug}-{slug_date(r['draw_date'])}", r["draw_date"]) for r in days]
        if region != "mb":
            for p in await provinces_of(conn, region):
                out.append((f"/xs-{p['code']}", None))
                out.append((f"/thong-ke-xs-{p['code']}", None))
    out += [("/vietlott", None), ("/xs-dien-toan", None)]
    out += await news_sitemap_entries(conn)
    for g in GAMES.values():
        days = await (await conn.execute(
            """SELECT DISTINCT draw_date FROM lottery_draws WHERE province_code = %s AND current_version IS NOT NULL
                ORDER BY draw_date DESC""", (g.code,))).fetchall()
        if not days:
            out.append((f"/{g.slug}", None))
        if days:
            out.append((f"/{g.slug}", days[0]["draw_date"]))
            if g.code in ("power655", "mega645"):
                out.append((f"/thong-ke-{g.slug}", days[0]["draw_date"]))
        out += [(f"/{g.slug}-{slug_date(r['draw_date'])}", r["draw_date"]) for r in days]
    return out


# ---------------- tin tức ----------------
NEWS_COLS = ("id, kind, topic, slug, title, summary, body, region_code, draw_ids, ref_date, source_name, source_url, "
             "feed_code, published_at, updated_at")
NEWS_TOPICS = {"ket-qua": ["region_day"], "vietlott": ["vietlott_draw"], "thong-ke": ["weekly_stats"], "bao-chi": ["external"]}
NEWS_TOPIC_LABEL = {"region_day": "Kết quả", "vietlott_draw": "Vietlott", "weekly_stats": "Thống kê", "external": "Báo chí"}


async def news_count(conn, topics: list[str] | None = None) -> int:
    if topics:
        sql, args = "SELECT count(*) AS n FROM news_articles WHERE NOT hidden AND topic = ANY(%s)", (topics,)
    else:
        sql, args = "SELECT count(*) AS n FROM news_articles WHERE NOT hidden", ()
    r = await (await conn.execute(sql, args)).fetchone()
    return int(r["n"]) if r else 0


async def news_list(conn, limit: int = 20, offset: int = 0, topics: list[str] | None = None) -> tuple[list[dict], int]:
    """Bài hiển thị được, mới nhất trước; trả (danh sách, tổng số)."""
    where = "NOT hidden" + (" AND topic = ANY(%s)" if topics else "")
    args = ((topics,) if topics else ()) + (int(limit), int(offset))
    rows = await (await conn.execute(
        f"SELECT {NEWS_COLS} FROM news_articles WHERE {where} ORDER BY published_at DESC, id DESC LIMIT %s OFFSET %s", args)).fetchall()
    return list(rows), await news_count(conn, topics)


async def news_by_slug(conn, slug: str) -> dict | None:
    return await (await conn.execute(
        f"SELECT {NEWS_COLS} FROM news_articles WHERE NOT hidden AND kind = 'auto' AND slug = %s LIMIT 1", (slug,))).fetchone()


async def news_sitemap_entries(conn) -> list[tuple[str, date | None]]:
    out: list[tuple[str, date | None]] = []
    latest = await (await conn.execute("SELECT max(published_at) AS d FROM news_articles WHERE NOT hidden")).fetchone()
    d = latest.get("d") if latest else None
    out.append(("/tin-tuc", d.date() if isinstance(d, datetime) else d))
    rows = await (await conn.execute(
        "SELECT slug, published_at, updated_at FROM news_articles WHERE NOT hidden AND kind = 'auto' AND slug IS NOT NULL "
        "ORDER BY published_at DESC LIMIT 5000")).fetchall()
    for r in rows:
        if not r.get("slug"):
            continue
        t = r.get("updated_at") or r.get("published_at")
        out.append((f"/tin-tuc/{r['slug']}", t.date() if isinstance(t, datetime) else None))
    return out


def compact(game, d: dict) -> str:
    """Kết quả một kỳ viết gọn trên một dòng (dùng cho danh sách và tin nhắn)."""
    pr = d["prizes"]
    if game.kind == "pick":
        return " ".join(pr.get("main", [])) + (f" + {pr['special'][0]}" if pr.get("special") else "")
    if game.kind == "dice":
        nums = pr.get("main", [])
        return " ".join(nums) + (f" (tổng {sum(int(n) for n in nums)})" if nums else "")
    return "; ".join(f"{name}: {' '.join(pr.get(code, []))}" for code, name, _c, _w in game.prizes)


def keno_stats(d: dict) -> dict:
    nums = [int(n) for n in d["prizes"].get("main", [])]
    return {"small": sum(1 for n in nums if n <= 40), "big": sum(1 for n in nums if n > 40),
            "even": sum(1 for n in nums if n % 2 == 0), "odd": sum(1 for n in nums if n % 2)}


async def region_draws(conn, region: str, limit: int) -> list[dict]:
    """K kỳ gần nhất của cả miền (miền Nam, Trung: mỗi đài mỗi ngày là một kỳ)."""
    return await _draws(conn, "d.region_code = %s", (region,), limit=limit, order="d.draw_date DESC, p.name")
