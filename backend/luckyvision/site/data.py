"""Truy vấn dữ liệu cho các trang công khai (đã công bố)."""
from __future__ import annotations

from datetime import date, timedelta

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
