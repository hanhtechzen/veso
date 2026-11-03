"""Trang của tôi: kết quả mới nhất của tỉnh yêu thích và tự dò các bộ số yêu thích."""
from __future__ import annotations

from ..domain.games import GAMES
from . import data as D

PRIZE_LABEL = {"db": "Giải Đặc biệt", "g1": "Giải Nhất", "g2": "Giải Nhì", "g3": "Giải Ba", "g4": "Giải Tư",
               "g5": "Giải Năm", "g6": "Giải Sáu", "g7": "Giải Bảy", "g8": "Giải Tám"}


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
                res["check"] = {"date": ds[0]["draw_date"].isoformat(), "seq": ds[0]["draw_seq"], "hits": hit,
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
                res["check"] = {"date": ds[0]["draw_date"].isoformat(), "hits": got if isinstance(got, list) else list(got),
                                "text": f"{D.dmy(ds[0]['draw_date'])}: {text}"}
        out_sets.append(res)
    return {"provinces": out_provs, "sets": out_sets}
