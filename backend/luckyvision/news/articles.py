"""Bài tin tự sinh từ kết quả đã công bố. Thuần (không truy cập CSDL); nội dung chỉ nêu số liệu, không nhận định hay dự đoán."""
from __future__ import annotations

from datetime import date, timedelta

from ..domain.games import GAMES
from ..site.data import REGION_SLUG, dmy, gan_stats, head_tail, slug_date

REGION_TITLES = {"mb": "Miền Bắc", "mn": "Miền Nam", "mt": "Miền Trung"}
VIETLOTT_GAMES = ("power655", "mega645")


def _name(d: dict) -> str:
    return d.get("province_name") or d.get("pname") or d.get("province_code") or ""


def _loto_ints(d: dict) -> list[int]:
    return [int(n) for n in d.get("loto") or []]


def _first(d: dict, code: str) -> str | None:
    v = (d.get("prizes") or {}).get(code) or []
    return v[0] if v else None


def _base(kind_topic: str, **kw) -> dict:
    return {"kind": "auto", "topic": kind_topic, "source_name": None, "source_url": None, "feed_code": None, **kw}


def region_day_article(region: str, day: date, draws: list[dict]) -> dict:
    if region not in REGION_TITLES:
        raise ValueError(f"Miền không hợp lệ: {region}")
    rname, rslug = REGION_TITLES[region], REGION_SLUG[region]
    day_link = f"/{rslug}-{slug_date(day)}"
    stations, parts = [], []
    for d in draws:
        db, g1 = _first(d, "db"), _first(d, "g1")
        st = {"name": _name(d), "code": d.get("province_code"), "db": db,
              "link": f"/xs-{d['province_code']}" if region != "mb" and d.get("province_code") else day_link}
        if g1:
            st["g1"] = g1
        stations.append(st)
        if region != "mb" and db:
            parts.append(f"{st['name']} {db}")
    dmy_s = dmy(day)
    if region == "mb":
        db, g1 = (stations[0]["db"], stations[0].get("g1")) if stations else (None, None)
        summary = f"Kết quả xổ số {rname} ngày {dmy_s}"
        if db:
            summary += f": giải đặc biệt {db}" + (f", giải nhất {g1}" if g1 else "")
        summary += "."
    else:
        summary = f"Kết quả xổ số {rname} ngày {dmy_s}, giải đặc biệt: " + "; ".join(parts) + "." if parts \
            else f"Kết quả xổ số {rname} ngày {dmy_s}."
    body = {"region": region, "date": day.isoformat(), "stations": stations, "link": day_link,
            "stats_link": f"/thong-ke-{rslug}"}
    lotos = [f"{n:02d}" for d in draws for n in _loto_ints(d)]
    if lotos:
        ht = head_tail(lotos)
        body["head_tail"] = {"dau": {str(k): v for k, v in ht["dau"].items()},
                             "duoi": {str(k): v for k, v in ht["duoi"].items()}}
    return _base("region_day", dedupe_key=f"region_day:{region}:{day.isoformat()}", slug=f"ket-qua-{rslug}-{slug_date(day)}",
                 title=f"Kết quả xổ số {rname} ({rslug.upper()}) ngày {dmy_s}", summary=summary, body=body,
                 region_code=region, draw_ids=[d["id"] for d in draws], ref_date=day)


def vietlott_article(game_code: str, d: dict) -> dict:
    if game_code not in VIETLOTT_GAMES:
        raise ValueError(f"Chỉ viết bài cho {', '.join(VIETLOTT_GAMES)}")
    g = GAMES[game_code]
    pr = d.get("prizes") or {}
    main, special = list(pr.get("main") or []), list(pr.get("special") or [])
    seq = d.get("draw_seq")
    day = d["draw_date"]
    head = f"Kết quả {g.name} kỳ #{seq:05d} ngày {dmy(day)}"
    summary = f"{head}: {' '.join(main)}" + (f", số đặc biệt {special[0]}" if special else "") + "."
    body = {"game": game_code, "game_name": g.name, "draw_seq": seq, "date": day.isoformat(), "numbers": main,
            "special": special[0] if special else None, "link": f"/{g.slug}", "day_link": f"/{g.slug}-{slug_date(day)}"}
    return _base("vietlott_draw", dedupe_key=f"vietlott_draw:{d['id']}", slug=f"{g.slug}-ky-{seq:05d}-{slug_date(day)}",
                 title=head, summary=summary, body=body, region_code=g.region, draw_ids=[d["id"]], ref_date=day)


def weekly_article(region: str, monday: date, draws: list[dict]) -> dict:
    if monday.weekday() != 0:
        raise ValueError("Ngày bắt đầu tuần phải là thứ Hai")
    if region not in REGION_TITLES:
        raise ValueError(f"Miền không hợp lệ: {region}")
    sunday = monday + timedelta(days=6)
    rname, rslug = REGION_TITLES[region], REGION_SLUG[region]
    by_day: dict[date, list[int]] = {}
    for d in draws:
        by_day.setdefault(d["draw_date"], []).extend(_loto_ints(d))
    freq: dict[int, int] = {}
    for lotos in by_day.values():
        for n in lotos:
            freq[n] = freq.get(n, 0) + 1
    hot = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:5]
    days_sorted = [{"loto": by_day[k]} for k in sorted(by_day)]
    gan = gan_stats(days_sorted, top=5)["gan"] if days_sorted else []
    span = f"{monday.strftime('%d/%m')} - {dmy(sunday)}"
    summary = f"Thống kê xổ số {rname} tuần {span}: {len(by_day)} ngày quay, {len(draws)} kỳ."
    if hot:
        summary += " Về nhiều nhất: " + ", ".join(f"{n:02d} ({c} lần)" for n, c in hot) + "."
    body = {"region": region, "from": monday.isoformat(), "to": sunday.isoformat(), "days": len(by_day), "draws": len(draws),
            "hot": [{"number": f"{n:02d}", "count": c} for n, c in hot],
            "gan": [{"number": f"{n:02d}", "days": g} for n, g in gan],
            "link": f"/thong-ke-{rslug}"}
    return _base("weekly_stats", dedupe_key=f"weekly:{region}:{monday.isoformat()}",
                 slug=f"thong-ke-tuan-{rslug}-{slug_date(monday)}", title=f"Thống kê xổ số {rname} tuần {span}",
                 summary=summary, body=body, region_code=region, draw_ids=[d["id"] for d in draws], ref_date=monday)
