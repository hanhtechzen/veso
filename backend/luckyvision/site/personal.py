"""Trang của tôi: kết quả mới nhất của tỉnh yêu thích và tự dò các bộ số yêu thích."""
from __future__ import annotations

from datetime import date, datetime

from ..config import VN_TZ
from ..domain.games import GAMES
from . import data as D

PRIZE_LABEL = {"db": "Giải Đặc biệt", "g1": "Giải Nhất", "g2": "Giải Nhì", "g3": "Giải Ba", "g4": "Giải Tư",
               "g5": "Giải Năm", "g6": "Giải Sáu", "g7": "Giải Bảy", "g8": "Giải Tám"}


def number_stats(draws: list[tuple[date, list[str]]], numbers: list[str], today: date) -> list[dict]:
    """Thống kê lịch sử của từng lô: lần về gần nhất, số ngày chưa về (tính đến hôm nay) và số lần về trong 30/90 ngày.
    `draws` là các (ngày quay, danh sách lô 2 chữ số); một số về nhiều lần trong ngày được đếm từng lần."""
    out = []
    for num in numbers:
        last: date | None = None
        c30 = c90 = 0
        for day, lotos in draws:
            delta = (today - day).days
            if delta < 0:
                continue
            k = sum(1 for x in lotos if x == num)
            if not k:
                continue
            if last is None or day > last:
                last = day
            if delta < 30:
                c30 += k
            if delta < 90:
                c90 += k
        out.append({"number": num, "last_date": last, "gan_days": (today - last).days if last else None,
                    "count30": c30, "count90": c90})
    return out


def _draw_numbers(g, d: dict) -> list[dict]:
    """Số của kỳ quay dạng có cấu trúc để vẽ chip: [{"n": "27", "sp": False}]; số đặc biệt đánh dấu sp."""
    pr = d["prizes"]
    if g is None:
        return [{"n": n, "sp": True} for n in pr.get("db", [])] + [{"n": n, "sp": False} for n in pr.get("g1", [])]
    if g.kind == "pick" or g.kind == "dice":
        return [{"n": n, "sp": False} for n in pr.get("main", [])] + [{"n": n, "sp": True} for n in pr.get("special", [])]
    return []


async def my_numbers(conn, user_id: int) -> list[dict]:
    """Thống kê lịch sử các bộ số lô yêu thích của thành viên (không phải dự đoán)."""
    sets = await (await conn.execute(
        "SELECT id, scope, numbers, label FROM user_fav_sets WHERE user_id = %s AND kind = 'lo' ORDER BY created_at",
        (user_id,))).fetchall()
    today = datetime.now(VN_TZ).date()
    cache: dict[str, list[tuple[date, list[str]]]] = {}
    out = []
    for s in sets:
        sc = s["scope"]
        if sc not in cache:
            ds = await D.region_range(conn, sc, 365) if sc in ("mb", "mn", "mt") else await D.province_draws(conn, sc, 200)
            cache[sc] = [(d["draw_date"], [f"{n:02d}" for n in d["loto"]]) for d in ds]
        out.append({"id": s["id"], "scope": sc, "label": s["label"], "numbers": number_stats(cache[sc], list(s["numbers"]), today)})
    return out


async def _scope_draws(conn, scope: str) -> list[dict]:
    """Các kỳ mới nhất của một phạm vi: cả miền (mọi đài trong ngày gần nhất) hoặc một đài."""
    if scope in ("mb", "mn", "mt"):
        day = await D.latest_day(conn, scope)
        return await D.day_draws(conn, scope, day) if day else []
    return await D.province_draws(conn, scope, 1)


async def dashboard(conn, user_id: int) -> dict:
    provs = await (await conn.execute(
        """SELECT p.code, p.name, p.region_code FROM user_fav_provinces f JOIN provinces p ON p.code = f.province_code
            WHERE f.user_id = %s ORDER BY f.created_at""", (user_id,))).fetchall()
    sets = await (await conn.execute(
        "SELECT id, kind, scope, numbers, label FROM user_fav_sets WHERE user_id = %s ORDER BY created_at", (user_id,))).fetchall()
    out_provs = []
    for p in provs:
        g = GAMES.get(p["code"])
        ds = await D.game_draws(conn, p["code"], limit=1) if g else await D.province_draws(conn, p["code"], 1)
        d = ds[0] if ds else None
        item = {"code": p["code"], "name": p["name"], "region": p["region_code"], "draw": None}
        if d:
            slug = g.slug if g else D.REGION_SLUG.get(p["region_code"], "")
            item["draw"] = {"date": d["draw_date"].isoformat(), "summary": D.compact(g, d) if g else
                            f"ĐB {d['prizes'].get('db', ['?'])[0]} · G1 {d['prizes'].get('g1', ['?'])[0]}",
                            "numbers": _draw_numbers(g, d),
                            "loto": [f"{x:02d}" for x in d["loto"]], "url": f"/{slug}-{D.slug_date(d['draw_date'])}" if slug else ""}
        out_provs.append(item)
    out_sets = []
    for s in sets:
        res = {"id": s["id"], "kind": s["kind"], "scope": s["scope"], "numbers": s["numbers"], "label": s["label"], "check": None}
        if s["kind"] == "pick" and s["scope"] in GAMES:
            ds = await D.game_draws(conn, s["scope"], limit=1)
            if ds:
                main = set(ds[0]["prizes"].get("main", []))
                hit = [n for n in s["numbers"] if n in main]
                res["check"] = {"date": ds[0]["draw_date"].isoformat(), "seq": ds[0]["draw_seq"], "hits": hit, "hit_numbers": hit,
                                "text": f"Trùng {len(hit)}/{len(s['numbers'])} số với kỳ {ds[0]['draw_seq'] or ''} ({D.dmy(ds[0]['draw_date'])})"}
        elif s["kind"] in ("lo", "ticket"):
            ds = await _scope_draws(conn, s["scope"])
            if ds:
                if s["kind"] == "lo":
                    hits = {n: [d["pname"] for d in ds if int(n) in d["loto"]] for n in s["numbers"]}
                    got = {n: v for n, v in hits.items() if v}
                    text = ("Về: " + "; ".join(f"{n} ({', '.join(v)})" for n, v in got.items())) if got else "Không số nào về"
                else:
                    wins = []
                    for t in s["numbers"]:
                        for d in ds:
                            for k, nums in d["prizes"].items():
                                for n in nums:
                                    if len(t) >= len(n) and t.endswith(n):
                                        wins.append(f"vé {t} trúng {PRIZE_LABEL.get(k, k)} đài {d['pname']}")
                    got, text = wins, ("; ".join(wins) if wins else "Không vé nào trúng giải chính")
                    won = [t for t in s["numbers"] if any(w.startswith(f"vé {t} ") for w in wins)]
                hit_nums = list(got) if s["kind"] == "lo" else won
                res["check"] = {"date": ds[0]["draw_date"].isoformat(), "hits": got if isinstance(got, list) else list(got),
                                "hit_numbers": hit_nums,
                                "text": f"{D.dmy(ds[0]['draw_date'])}: {text}"}
        out_sets.append(res)
    return {"provinces": out_provs, "sets": out_sets}
