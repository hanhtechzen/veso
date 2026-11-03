"""Các trang công khai do máy chủ tạo sẵn HTML, tối ưu cho tìm kiếm (SEO).

Đường dẫn theo cách người Việt hay tìm: /xsmb, /xsmb-29-10-2026, /xs-tp-hcm, /vietlott-power-655,
/so-ket-qua-xsmn-30-ngay, /thong-ke-xsmb, /thong-ke-xs-da-nang; kèm /sitemap.xml và /robots.txt.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..domain.games import GAMES
from . import data as D

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(weekday=D.weekday, compact=D.compact, keno_stats=D.keno_stats)
# Menu giống bản Công cụ: hàng chính 4 mục, hàng phụ đổi theo mục đang xem
NAV = [("/", "Kết quả", "kq"), ("/vietlott-power-655", "Power 6/55", "pw"), ("/thong-ke-xsmb", "Thống kê", "tk"),
       ("/du-doan.html", "Dự báo", "db"), ("/cong-cu/#may-thoi-gian", "Công cụ", "cc")]
SUBNAV = {
    "kq": [("/xsmb", "XSMB", "mb"), ("/xsmn", "XSMN", "mn"), ("/xsmt", "XSMT", "mt"), ("/vietlott", "Vietlott", "vietlott"),
           ("/xs-dien-toan", "Điện toán", "dientoan"), ("/so-ket-qua-xsmb-30-ngay", "Sổ kết quả", "so"), ("/lich-quay-xo-so", "Lịch quay", "lich")],
    "tk": [("/thong-ke-xsmb", "Miền Bắc", "mb"), ("/thong-ke-xsmn", "Miền Nam", "mn"), ("/thong-ke-xsmt", "Miền Trung", "mt"),
           ("/thong-ke-vietlott-power-655", "Power 6/55", "power655"), ("/thong-ke-vietlott-mega-645", "Mega 6/45", "mega645"),
           ("/so-sanh", "So sánh số", "ss"), ("/du-doan.html", "Xác suất từng số", "xs"), ("/cong-cu/#dau-truong", "Đấu trường mô hình", "dt")],
    "pw": [("/vietlott-power-655", "Kết quả", "pw-kq"), ("/thong-ke-vietlott-power-655", "Thống kê", "pw-tk"),
           ("/cong-cu/#trang-chu", "Kỳ tới", "x"), ("/cong-cu/#dau-truong", "Đấu trường", "x"), ("/cong-cu/#may-thoi-gian", "Máy thời gian", "x"),
           ("/cong-cu/#tao-so", "Tạo bộ số", "x"), ("/cong-cu/#so-du-doan", "Sổ dự đoán", "x"), ("/cong-cu/#do-ve", "Dò vé", "x")],
}
GAME_BY_SLUG = {g.slug: g for g in GAMES.values()}


def _jsonld(site: str, crumbs: list[tuple[str, str]], extra: list[dict] | None = None) -> str:
    graph = [{"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": site + href} for i, (href, name) in enumerate(crumbs)]}]
    graph += extra or []
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")


def _render(request: Request, tpl: str, *, title: str, description: str, crumbs: list[tuple[str, str]],
            active: str | None = None, max_age: int = 60, status: int = 200, extra_ld: list[dict] | None = None, **kw) -> HTMLResponse:
    s = request.app.state.settings
    site = s.site_url.rstrip("/")
    path = request.url.path
    if path.startswith("/vietlott-power-655") or path.startswith("/thong-ke-vietlott-power-655"):
        section, sub_active = "pw", ("pw-tk" if path.startswith("/thong-ke") else "pw-kq")
    else:
        section = "tk" if path.startswith(("/thong-ke", "/so-sanh")) else "kq"
        sub_active = ("so" if path.startswith("/so-ket-qua") else "lich" if path.startswith("/lich-quay")
                      else "ss" if path.startswith("/so-sanh") else active)
    ctx = {"title": title, "description": description, "canonical": site + path, "site_url": site,
           "site_name": s.site_name, "nav": NAV, "section": section, "subnav": SUBNAV[section], "sub_active": sub_active,
           "active": active, "breadcrumbs": crumbs if len(crumbs) > 1 else None,
           "jsonld": _jsonld(site, crumbs, extra_ld), "short": D.PRIZE_SHORT, **kw}
    resp = templates.TemplateResponse(request, tpl, ctx, status_code=status)
    resp.headers["Cache-Control"] = f"public, max-age={max_age}, stale-while-revalidate=600"
    return resp


def _not_found(request: Request, message: str) -> HTMLResponse:
    return _render(request, "notfound.html", title="Không tìm thấy trang | LuckyVision", description=message,
                   crumbs=[("/", "Trang chủ")], status=404, noindex=True, message=message, max_age=60)


def _summary(region: str, draws: list[dict]) -> str:
    """Đoạn tóm tắt tự động, mỗi ngày một nội dung khác nhau."""
    if not draws:
        return ""
    dbs = ", ".join(f"{d['pname']} {d['prizes'].get('db', ['?'])[0]}" for d in draws) if region != "mb" else draws[0]["prizes"].get("db", ["?"])[0]
    counts: dict[int, int] = {}
    for d in draws:
        for n in d["loto"]:
            counts[n] = counts.get(n, 0) + 1
    top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    tops = ", ".join(f"{n:02d} ({c} lần)" for n, c in top)
    heads = {h: sum(1 for d in draws for n in d["loto"] if n // 10 == h) for h in range(10)}
    empty = [str(h) for h, c in heads.items() if c == 0]
    s = f"Giải đặc biệt: {dbs}. Lô về nhiều nhất: {tops}."
    if empty:
        s += f" Đầu {', '.join(empty)} không có lô nào về."
    return s


# ---------------- trang chủ ----------------
@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    sections, games = [], []
    async with request.app.state.pool.connection() as conn:
        for r, slug in D.REGION_SLUG.items():
            day = await D.latest_day(conn, r)
            draws = await D.day_draws(conn, r, day) if day else []
            sections.append({"region": r, "slug": slug, "url": f"/{slug}", "title": f"Xổ số {D.REGION_NAMES[r]}",
                             "when": f"{D.weekday(day)} {D.dmy(day)}" if day else "", "draws": draws, "display": D.DISPLAY[r]})
        for g in GAMES.values():
            if g.code not in ("power655", "mega645"):
                continue
            ds = await D.game_draws(conn, g.code, limit=1)
            games.append({"slug": g.slug, "name": g.name, "draw": ds[0] if ds else None, "g": g,
                          "when": f"{D.weekday(ds[0]['draw_date'])} {D.dmy(ds[0]['draw_date'])}" if ds else ""})
    s = request.app.state.settings
    org = {"@type": "WebSite", "name": s.site_name, "url": s.site_url.rstrip("/") + "/", "inLanguage": "vi-VN"}
    return _render(request, "home.html", title="Kết quả xổ số hôm nay XSMB, XSMN, XSMT, Vietlott | LuckyVision",
                   description="Kết quả xổ số miền Bắc, miền Nam, miền Trung, Vietlott Power 6/55, Mega 6/45 hôm nay, đối chiếu nhiều nguồn; thống kê lô gan, sổ kết quả và dự báo được chấm điểm công khai.",
                   crumbs=[("/", "Trang chủ")], extra_ld=[org], sections=sections, games=games)


# ---------------- kết quả theo miền và ngày ----------------
async def _region_day(request: Request, region: str, day: date | None, is_latest: bool):
    slug = D.REGION_SLUG[region]
    async with request.app.state.pool.connection() as conn:
        latest = await D.latest_day(conn, region)
        day = day or latest
        if not day:
            return _not_found(request, f"Chưa có kết quả xổ số {D.REGION_NAMES[region]}.")
        draws = await D.day_draws(conn, region, day)
        prev, nxt = await D.neighbour_days(conn, region, day)
    if not draws:
        return _not_found(request, f"Không có kết quả xổ số {D.REGION_NAMES[region]} ngày {D.dmy(day)}. Có thể ngày này không quay hoặc chưa có kết quả.")
    code = slug.upper()
    h1 = f"{code} {D.dmy(day)}: kết quả xổ số {D.REGION_NAMES[region]} {D.weekday(day).lower()}"
    title = (f"{code} hôm nay {D.dmy(day)}, kết quả xổ số {D.REGION_NAMES[region]}" if is_latest
             else f"{code} {D.dmy(day)}, kết quả xổ số {D.REGION_NAMES[region]} {D.weekday(day)}") + " | LuckyVision"
    provs = ", ".join(d["pname"] for d in draws) if region != "mb" else ""
    desc = f"Kết quả {code} {D.weekday(day)} ngày {D.dmy(day)}" + (f" ({provs})" if provs else "") + ": đầy đủ giải đặc biệt đến giải " + ("bảy" if region == "mb" else "tám") + ", bảng lô tô đầu đuôi, in bảng dò vé."
    crumbs = [("/", "Trang chủ"), (f"/{slug}", f"Xổ số {D.REGION_NAMES[region]}")] + ([] if is_latest else [(f"/{slug}-{D.slug_date(day)}", D.dmy(day))])
    old = (date.today() - day).days > 2
    return _render(request, "day.html", title=title, description=desc, crumbs=crumbs, active=region, region=region, slug=slug,
                   region_name=D.REGION_NAMES[region], h1=h1, summary=_summary(region, draws), draws=draws, display=D.DISPLAY[region],
                   iso=day.isoformat(), prev=prev, next=nxt,
                   prev_url=f"/{slug}-{D.slug_date(prev)}" if prev else None, prev_label=D.dmy(prev) if prev else "",
                   next_url=f"/{slug}-{D.slug_date(nxt)}" if nxt else None, next_label=D.dmy(nxt) if nxt else "",
                   max_age=86400 if old else 60)


for _r, _slug in D.REGION_SLUG.items():
    def _make(region=_r, slug=_slug):
        async def latest(request: Request):
            return await _region_day(request, region, None, True)

        async def by_day(request: Request, ds: str):
            day = D.parse_slug_date(ds)
            if not day:
                return _not_found(request, "Ngày không hợp lệ. Đường dẫn có dạng /" + slug + "-29-10-2026.")
            return await _region_day(request, region, day, False)
        router.add_api_route(f"/{slug}", latest, response_class=HTMLResponse, include_in_schema=False)
        router.add_api_route(f"/{slug}-{{ds}}", by_day, response_class=HTMLResponse, include_in_schema=False)
    _make()


@router.get("/chon-ngay")
async def jump(mien: str, ngay: date):
    target = f"/{mien}-{D.slug_date(ngay)}" if mien in D.SLUG_REGION else f"/{mien}-{D.slug_date(ngay)}" if mien in GAME_BY_SLUG else "/"
    return RedirectResponse(target, status_code=302)


# ---------------- trang từng đài ----------------
async def province_page(request: Request, code: str):
    async with request.app.state.pool.connection() as conn:
        p = await D.province(conn, code)
        if not p or p["region_code"] not in ("mn", "mt"):
            return _not_found(request, "Không có đài xổ số này.")
        draws = await D.province_draws(conn, code, 10)
        sched = await (await conn.execute("SELECT DISTINCT iso_weekday FROM draw_schedules WHERE province_code = %s AND (valid_to IS NULL OR valid_to >= current_date) ORDER BY 1", (code,))).fetchall()
    region = p["region_code"]
    days = ", ".join(D.WEEKDAY[r["iso_weekday"] - 1].lower() for r in sched)
    summary = f"Xổ số {p['name']} quay vào {days} hằng tuần, lúc {'16:15' if region == 'mn' else '17:15'}." + (
        f" Kỳ gần nhất ngày {D.dmy(draws[0]['draw_date'])}, giải đặc biệt {draws[0]['prizes'].get('db', ['?'])[0]}." if draws else "")
    return _render(request, "province.html", title=f"Xổ số {p['name']}: kết quả mới nhất, các kỳ trước | LuckyVision",
                   description=f"Kết quả xổ số {p['name']} mới nhất và 10 kỳ gần đây; lịch quay {days}; thống kê lô gan {p['name']}.",
                   crumbs=[("/", "Trang chủ"), (f"/{D.REGION_SLUG[region]}", f"Xổ số {D.REGION_NAMES[region]}"), (f"/xs-{code}", p["name"])],
                   active=region, region=region, slug=D.REGION_SLUG[region], region_name=D.REGION_NAMES[region], code=code, pname=p["name"],
                   h1=f"Xổ số {p['name']}", summary=summary, draws=draws, display=D.DISPLAY[region],
                   latest_label=f"{D.weekday(draws[0]['draw_date'])} {D.dmy(draws[0]['draw_date'])}" if draws else "", max_age=300)


# ---------------- Vietlott ----------------
async def _game_page(request: Request, g, day: date | None):
    async with request.app.state.pool.connection() as conn:
        recent = await D.game_draws(conn, g.code, limit=30 if g.multi_daily else 20)
        day_draws = await D.game_draws(conn, g.code, day=day) if day else []
    if day and not day_draws:
        return _not_found(request, f"Không có kỳ quay {g.name} ngày {D.dmy(day)}.")
    main = day_draws[0] if day else (recent[0] if recent else None)
    odds = (f"Xác suất trúng giải cao nhất với một vé: 1 trên {g.jackpot_odds:,}".replace(",", ".") + "."
            if g.kind == "pick" and g.jackpot_odds and g.code != "keno" else "")
    if main:
        ky = f"Kỳ {main['draw_seq']:0{g.seq_width}d}, " if main["draw_seq"] else ""
        summary = f"{ky}{D.weekday(main['draw_date']).lower()} {D.dmy(main['draw_date'])}: {D.compact(g, main)}."
        summary = summary[0].upper() + summary[1:]
    else:
        summary = ("Chưa có kết quả. Loại xổ số này chưa có nguồn tự động; kết quả được quản trị viên nhập và xác minh."
                   if g.family == "dientoan" else "Chưa có kết quả.")
    when = f" {D.dmy(day)}" if day else " hôm nay"
    hub = ("/vietlott", "Vietlott") if g.family == "vietlott" else ("/xs-dien-toan", "Xổ số điện toán")
    crumbs = [("/", "Trang chủ"), hub, (f"/{g.slug}", g.name.replace("Vietlott ", ""))] + ([(f"/{g.slug}-{D.slug_date(day)}", D.dmy(day))] if day else [])
    return _render(request, "game.html", title=f"{g.name}{when}: kết quả, các kỳ trước | LuckyVision",
                   description=f"Kết quả {g.name}{when}. {summary} " + (g.schedule + ". " if g.schedule else "") + "Xem các kỳ trước và thống kê.",
                   crumbs=crumbs, active=g.family, region=g.code, g=g, h1=f"Kết quả {g.name}{when}", summary=summary, main=main,
                   day_draws=day_draws if (day and g.multi_daily) else [], recent=[] if day else recent, slug=g.slug, odds_text=odds,
                   max_age=86400 if day and (date.today() - day).days > 2 else (60 if g.multi_daily else 120))


# Đăng ký đường dẫn chính xác trước, đường dẫn có ngày sau; slug dài trước slug ngắn
# để /vietlott-max-3d-pro không bị hiểu là /vietlott-max-3d với ngày "pro".
_GAME_DAY_ROUTES = []
for _g in GAMES.values():
    def _make_g(g=_g):
        async def latest(request: Request):
            return await _game_page(request, g, None)

        async def by_day(request: Request, ds: str):
            day = D.parse_slug_date(ds)
            return await _game_page(request, g, day) if day else _not_found(request, "Ngày không hợp lệ.")
        router.add_api_route(f"/{g.slug}", latest, response_class=HTMLResponse, include_in_schema=False)
        _GAME_DAY_ROUTES.append((g.slug, by_day))
    _make_g()


async def _hub(request: Request, family: str):
    items = []
    async with request.app.state.pool.connection() as conn:
        for g in GAMES.values():
            if g.family != family:
                continue
            ds = await D.game_draws(conn, g.code, limit=1)
            items.append({"g": g, "d": ds[0] if ds else None})
    if family == "vietlott":
        title, h1 = "Kết quả Vietlott hôm nay: Power 6/55, Mega 6/45, Lotto 5/35, Max 3D, Keno, Bingo18 | LuckyVision", "Kết quả Vietlott"
        desc = "Kết quả mới nhất mọi trò chơi Vietlott: Power 6/55, Mega 6/45, Lotto 5/35, Max 3D, Max 3D Pro, Keno, Bingo18, lấy từ trang chính thức."
        lead = "Kết quả mới nhất của tất cả trò chơi Vietlott, lấy từ trang chính thức vietlott.vn."
    else:
        title, h1 = "Xổ số điện toán: 1*2*3, Thần Tài 4, 6x36 | LuckyVision", "Xổ số điện toán miền Bắc"
        desc = "Kết quả xổ số điện toán 1*2*3, Thần Tài 4 và 6x36 của Công ty XSKT Thủ đô."
        lead = "Kết quả xổ số điện toán 1*2*3, Thần Tài 4 và 6x36. Loại xổ số này chưa có nguồn tự động được kiểm chứng; kết quả do quản trị viên nhập và xác minh."
    path = "/vietlott" if family == "vietlott" else "/xs-dien-toan"
    return _render(request, "hub.html", title=title, description=desc, crumbs=[("/", "Trang chủ"), (path, h1)], active=family,
                   h1=h1, lead=lead, items=items, max_age=60)


@router.get("/vietlott", response_class=HTMLResponse)
async def hub_vietlott(request: Request):
    return await _hub(request, "vietlott")


@router.get("/xs-dien-toan", response_class=HTMLResponse)
async def hub_dientoan(request: Request):
    return await _hub(request, "dientoan")


# ---------------- sổ kết quả 30/60/90 ngày ----------------
@router.get("/so-ket-qua-{slug}-{n:int}-ngay", response_class=HTMLResponse)
async def so_ket_qua(request: Request, slug: str, n: int):
    region = D.SLUG_REGION.get(slug)
    if not region or n not in (30, 60, 90):
        return _not_found(request, "Sổ kết quả có 30, 60 hoặc 90 ngày cho XSMB, XSMN, XSMT.")
    async with request.app.state.pool.connection() as conn:
        draws = await D.region_range(conn, region, n)
    groups: list[dict] = []
    for d in draws:
        if not groups or groups[-1]["day"] != d["draw_date"]:
            groups.append({"day": d["draw_date"], "draws": []})
        groups[-1]["draws"].append(d)
    code = slug.upper()
    return _render(request, "so.html", title=f"Sổ kết quả {code} {n} ngày gần nhất | LuckyVision",
                   description=f"Sổ kết quả xổ số {D.REGION_NAMES[region]} {n} ngày: giải đặc biệt, giải nhất và lô tô từng kỳ, in được.",
                   crumbs=[("/", "Trang chủ"), (f"/{slug}", f"Xổ số {D.REGION_NAMES[region]}"), (request.url.path, f"Sổ {n} ngày")],
                   active=region, region=region, slug=slug, days=n, groups=groups, h1=f"Sổ kết quả {code} {n} ngày",
                   summary=f"{len(groups)} ngày quay, {len(draws)} kỳ, mới nhất ở trên cùng.", max_age=600)


# ---------------- thống kê lô gan ----------------
async def _stats(request: Request, region: str, code: str | None):
    async with request.app.state.pool.connection() as conn:
        p = await D.province(conn, code) if code else None
        if code and (not p or p["region_code"] != region):
            return _not_found(request, "Không có đài này.")
        provs = await D.provinces_of(conn, region) if region != "mb" else []
        if region == "mb":
            draws = (await D.region_range(conn, "mb", 365))[::-1]
        elif code:
            draws = (await D.province_draws(conn, code, 120))[::-1]
        else:
            draws = []
    slug = D.REGION_SLUG[region]
    name = p["name"] if p else D.REGION_NAMES[region]
    st = D.gan_stats(draws) if draws else None
    if region != "mb" and not code:
        h1, summary = f"Thống kê lô gan, tần suất xổ số {name}", "Chọn một đài để xem lô gan và tần suất lô tô của đài đó."
    else:
        h1 = f"Thống kê lô gan {name}"
        summary = f"Phân tích {len(draws)} kỳ quay gần nhất của {name}." if draws else "Chưa đủ dữ liệu."
    path = f"/thong-ke-xs-{code}" if code else f"/thong-ke-{slug}"
    crumbs = [("/", "Trang chủ"), (f"/{slug}", f"Xổ số {D.REGION_NAMES[region]}"), (path, "Thống kê" + (f" {name}" if p else ""))]
    return _render(request, "stats.html", title=f"{h1}: lô lâu chưa về, lô về nhiều | LuckyVision",
                   description=f"Lô gan, lô về nhiều và về ít của {name}, cập nhật sau mỗi kỳ quay. Kèm giải thích trung thực về xác suất.",
                   crumbs=crumbs, active=region, region=region, h1=h1, summary=summary, st=st, provinces=provs, current=code, max_age=600)


for _r, _slug in D.REGION_SLUG.items():
    def _make_s(region=_r, slug=_slug):
        async def page(request: Request):
            return await _stats(request, region, None)
        router.add_api_route(f"/thong-ke-{slug}", page, response_class=HTMLResponse, include_in_schema=False)
    _make_s()


async def stats_game(request: Request, g):
    async with request.app.state.pool.connection() as conn:
        draws = (await D.game_draws(conn, g.code, limit=300))[::-1]
    n = len(draws)
    freq = {k: 0 for k in range(1, g.main_max + 1)}
    last: dict[int, int] = {}
    for i, d in enumerate(draws):
        for x in d["prizes"].get("main", []):
            freq[int(x)] += 1
            last[int(x)] = i
    recent = draws[-100:]
    rf = {k: 0 for k in range(1, g.main_max + 1)}
    for d in recent:
        for x in d["prizes"].get("main", []):
            rf[int(x)] += 1
    gan = sorted(((k, n - 1 - last.get(k, -1)) for k in freq), key=lambda x: (-x[1], x[0]))[:12]
    hot = sorted(rf.items(), key=lambda x: (-x[1], x[0]))[:10]
    cold = sorted(rf.items(), key=lambda x: (x[1], x[0]))[:10]
    theory = g.main_count / g.main_max
    expected = round(theory * len(recent), 1)
    mx = max(rf.values()) if rf else 1
    return _render(request, "stats_pick.html", title=f"Thống kê {g.name}: số về nhiều, số lâu chưa về | LuckyVision",
                   description=f"Tần suất từng số {g.name} trong {len(recent)} kỳ gần nhất, số lâu chưa về, kèm xác suất lý thuyết {theory:.1%} mỗi số.",
                   crumbs=[("/", "Trang chủ"), (f"/{g.slug}", g.name.replace("Vietlott ", "")), (f"/thong-ke-{g.slug}", "Thống kê")],
                   active=g.code, region=g.code, g=g, h1=f"Thống kê {g.name}", draws=n, recent=len(recent), rf=rf, mx=mx,
                   gan=gan, hot=hot, cold=cold, theory=theory, expected=expected, max_age=600)


async def stats_province(request: Request, code: str):
    async with request.app.state.pool.connection() as conn:
        p = await D.province(conn, code)
    if not p or p["region_code"] not in ("mn", "mt"):
        return _not_found(request, "Không có đài này.")
    return await _stats(request, p["region_code"], code)


# ---------------- sitemap, robots ----------------
@router.get("/sitemap.xml")
async def sitemap(request: Request):
    site = request.app.state.settings.site_url.rstrip("/")
    async with request.app.state.pool.connection() as conn:
        entries = [("/", None)] + await D.sitemap_entries(conn)
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod in entries:
        body.append("<url><loc>" + escape(site + path) + "</loc>" + (f"<lastmod>{lastmod.isoformat()}</lastmod>" if lastmod else "") + "</url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/robots.txt")
async def robots(request: Request):
    site = request.app.state.settings.site_url.rstrip("/")
    txt = "User-agent: *\nAllow: /\nDisallow: /v1/\nDisallow: /admin.html\nDisallow: /chon-ngay\n\nSitemap: " + site + "/sitemap.xml\n"
    return PlainTextResponse(txt, headers={"Cache-Control": "public, max-age=86400"})


# Đường dẫn chung đặt cuối cùng để không che các trang trò chơi (vd. /xs-dien-toan-123, /xs-than-tai-4)
for _slug, _fn in sorted(_GAME_DAY_ROUTES, key=lambda x: -len(x[0])):
    router.add_api_route(f"/{_slug}-{{ds}}", _fn, response_class=HTMLResponse, include_in_schema=False)
for _g in (GAMES["power655"], GAMES["mega645"]):
    def _make_st(g=_g):
        async def page(request: Request):
            return await stats_game(request, g)
        router.add_api_route(f"/thong-ke-{g.slug}", page, response_class=HTMLResponse, include_in_schema=False)
    _make_st()
router.add_api_route("/thong-ke-xs-{code}", stats_province, response_class=HTMLResponse, include_in_schema=False)
router.add_api_route("/xs-{code}", province_page, response_class=HTMLResponse, include_in_schema=False)


# ===================== Lịch mở thưởng =====================
@router.get("/lich-quay-xo-so", response_class=HTMLResponse)
async def schedule_page(request: Request):
    from datetime import datetime as _dt
    from ..config import VN_TZ
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT s.iso_weekday, s.draw_time, p.code, p.name, p.region_code FROM draw_schedules s
                 JOIN provinces p ON p.code = s.province_code
                WHERE p.active AND (s.valid_to IS NULL OR s.valid_to >= current_date) AND s.valid_from <= current_date
                  AND p.region_code IN ('mb', 'mn', 'mt') ORDER BY s.iso_weekday, p.region_code, p.name""")).fetchall()
    week = {i: {"mn": [], "mt": [], "mb": []} for i in range(1, 8)}
    times = {}
    for r in rows:
        week[r["iso_weekday"]][r["region_code"]].append({"code": r["code"], "name": r["name"]})
        times[r["region_code"]] = r["draw_time"].strftime("%H:%M")
    today = _dt.now(VN_TZ).isoweekday()
    vl = [g for g in GAMES.values() if g.family == "vietlott"]
    faq = [("Xổ số miền Nam quay lúc mấy giờ?", f"Xổ số miền Nam quay lúc {times.get('mn', '16:15')} hằng ngày, mỗi ngày 3–4 đài."),
           ("Xổ số miền Trung quay lúc mấy giờ?", f"Xổ số miền Trung quay lúc {times.get('mt', '17:15')} hằng ngày, mỗi ngày 2–3 đài."),
           ("Xổ số miền Bắc quay lúc mấy giờ?", f"Xổ số miền Bắc quay lúc {times.get('mb', '18:15')} tất cả các ngày trong tuần."),
           ("Vietlott Power 6/55 quay vào ngày nào?", "Power 6/55 quay thứ Ba, thứ Năm và thứ Bảy lúc 18:00; Mega 6/45 quay thứ Tư, thứ Sáu và Chủ nhật lúc 18:00.")]
    ld = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return _render(request, "schedule.html", title="Lịch quay xổ số ba miền và Vietlott trong tuần | LuckyVision",
                   description="Lịch mở thưởng xổ số miền Nam, miền Trung, miền Bắc theo từng ngày trong tuần, giờ quay và lịch các trò chơi Vietlott.",
                   crumbs=[("/", "Trang chủ"), ("/lich-quay-xo-so", "Lịch quay xổ số")], active=None, extra_ld=ld,
                   week=week, times=times, today=today, vl=vl, faq=faq, max_age=3600)


# ===================== So sánh các con số =====================
async def _compare_draws(conn, scope: str, ky: int):
    """(các kỳ cũ trước, kiểu chọn số?, mô tả phạm vi, khoảng số)."""
    if scope in GAMES and GAMES[scope].kind == "pick":
        g = GAMES[scope]
        return (await D.game_draws(conn, g.code, limit=ky))[::-1], True, g.name, range(1, g.main_max + 1), g
    if scope in ("mb", "xsmb"):
        return (await D.province_draws(conn, "mb", ky))[::-1], False, "Xổ số miền Bắc", range(0, 100), None
    if scope in ("mn", "mt", "xsmn", "xsmt"):
        r = scope[-2:]
        return (await D.region_draws(conn, r, ky))[::-1], False, f"Xổ số {D.REGION_NAMES[r]} (mọi đài)", range(0, 100), None
    p = await D.province(conn, scope)
    if p and p["region_code"] in ("mn", "mt"):
        return (await D.province_draws(conn, scope, ky))[::-1], False, f"Xổ số {p['name']}", range(0, 100), None
    return [], False, "", range(0, 100), None


@router.get("/so-sanh", response_class=HTMLResponse)
async def compare_page(request: Request, so: str = "", pham_vi: str = Query("mb", alias="pham-vi"), ky: int = 90):
    from .compare import analyze, parse_numbers
    ky = ky if ky in (30, 90, 180, 365) else 90
    async with request.app.state.pool.connection() as conn:
        provs = [p for r in ("mn", "mt") for p in await D.provinces_of(conn, r)]
        draws, pick, scope_name, uni, g = await _compare_draws(conn, pham_vi, ky)
    nums = parse_numbers(so, uni.start, uni.stop - 1)
    result = None
    if nums and draws:
        if pick:
            p = g.main_count / g.main_max
        else:
            avg_l = sum(len(d["loto"]) for d in draws) / len(draws)
            p = 1 - (0.99 ** avg_l)
        result = analyze(draws, nums, pick=pick, universe=uni, p_theory=p)
    fmt = (lambda x: f"{x:02d}")
    title = (f"So sánh {' và '.join(fmt(x) for x in nums)}, {scope_name}" if nums else "So sánh các con số") + " | LuckyVision"
    return _render(request, "compare.html", title=title,
                   description="So sánh tần suất, số kỳ chưa về, khoảng cách giữa các lần về và các số hay về cùng của 2–4 con số.",
                   crumbs=[("/", "Trang chủ"), ("/so-sanh", "So sánh các con số")], active=None, noindex=bool(so),
                   so=so, nums=nums, pham_vi=pham_vi, ky=ky, scope_name=scope_name, result=result, pick=pick, provs=provs,
                   games=[x for x in GAMES.values() if x.kind == "pick" and x.code not in ("keno",)], fmt=fmt, max_age=300)


# ===================== Tìm kiếm thông minh =====================
async def _ticket_answers(conn, it, today):
    from .personal import PRIZE_LABEL
    regions = [it.region] if it.region in ("mb", "mn", "mt") else ["mb", "mn", "mt"]
    out = []
    for r in regions:
        if it.day:
            days = [it.day]
        else:
            last = await D.latest_day(conn, r)
            days = [last - timedelta(days=k) for k in range(7)] if last else []
        for day in days:
            for d in await D.day_draws(conn, r, day):
                if it.province and d["province_code"] != it.province:
                    continue
                for t in it.tickets:
                    for k, nums in d["prizes"].items():
                        for n in nums:
                            if len(t) >= len(n) and t.endswith(n):
                                out.append({"title": f"Vé {t} trúng {PRIZE_LABEL.get(k, k)}",
                                            "desc": f"{d['pname']}, {D.weekday(day)} {D.dmy(day)} (số {n})",
                                            "url": f"/{D.REGION_SLUG[r]}-{D.slug_date(day)}"})
    return out


@router.get("/tim-kiem", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    from datetime import datetime as _dt
    from ..config import VN_TZ
    from .search import parse
    q = (q or "").strip()[:120]
    today = _dt.now(VN_TZ).date()
    answers, note = [], ""
    if q:
        async with request.app.state.pool.connection() as conn:
            provs = await (await conn.execute("SELECT code, name, region_code FROM provinces WHERE active")).fetchall()
            it = parse(q, provs, today)
            target = None
            if it.topic == "lich-quay":
                target = "/lich-quay-xo-so"
            elif it.game:
                g = GAMES[it.game]
                if it.seq:
                    r = await (await conn.execute("SELECT draw_date FROM lottery_draws WHERE province_code = %s AND draw_seq = %s AND current_version IS NOT NULL",
                                                  (g.code, it.seq))).fetchone()
                    target = f"/{g.slug}-{D.slug_date(r['draw_date'])}" if r else None
                    note = "" if r else f"Không tìm thấy kỳ {it.seq} của {g.name}."
                elif it.lo and g.kind == "pick":
                    target = f"/so-sanh?so={','.join(it.lo)}&pham-vi={g.code}"
                elif it.day:
                    target = f"/{g.slug}-{D.slug_date(it.day)}"
                else:
                    target = f"/{g.slug}"
            elif it.tickets:
                answers = await _ticket_answers(conn, it, today)
                note = "" if answers else "Không thấy vé nào trúng giải chính trong " + ("ngày đã chọn." if it.day else "7 ngày gần nhất.")
            elif it.lo:
                scope = it.province or it.region or "mb"
                target = f"/so-sanh?so={','.join(it.lo)}&pham-vi={scope}"
            elif it.topic == "thong-ke":
                target = f"/thong-ke-xs-{it.province}" if it.province and it.region != "mb" else f"/thong-ke-{D.REGION_SLUG.get(it.region or 'mb')}"
            elif it.topic == "so-ket-qua":
                target = f"/so-ket-qua-{D.REGION_SLUG.get(it.region or 'mb')}-30-ngay"
            elif it.region:
                if it.day:
                    target = f"/{D.REGION_SLUG[it.region]}-{D.slug_date(it.day)}"
                elif it.province and it.region != "mb":
                    target = f"/xs-{it.province}"
                else:
                    target = f"/{D.REGION_SLUG[it.region]}"
            elif it.day:
                answers = [{"title": f"Xổ số {D.REGION_NAMES[r]} {D.dmy(it.day)}", "desc": D.weekday(it.day),
                            "url": f"/{D.REGION_SLUG[r]}-{D.slug_date(it.day)}"} for r in ("mb", "mn", "mt")]
        if target:
            return RedirectResponse(target, status_code=302)
        if not answers and not note:
            note = f"Chưa hiểu “{q}”. Thử một trong các cách gõ bên dưới."
    return _render(request, "search.html", title=(f"Tìm “{q}”" if q else "Tìm kiếm") + " | LuckyVision",
                   description="Tìm nhanh kết quả xổ số theo ngày, theo đài, theo kỳ Vietlott, dò vé và so sánh số.",
                   crumbs=[("/", "Trang chủ"), ("/tim-kiem", "Tìm kiếm")], active=None, noindex=True, q=q, answers=answers, note=note, max_age=60)


# ===================== Tài khoản người dùng (giao diện) =====================
@router.get("/dang-nhap", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "user_login.html", title="Đăng nhập | LuckyVision", description="Đăng nhập để lưu tỉnh và bộ số yêu thích.",
                   crumbs=[("/", "Trang chủ"), ("/dang-nhap", "Đăng nhập")], noindex=True, mode="login", max_age=3600,
                   support_contact=request.app.state.settings.support_contact)


@router.get("/dang-ky", response_class=HTMLResponse)
async def register_page(request: Request):
    return _render(request, "user_login.html", title="Tạo tài khoản | LuckyVision", description="Tạo tài khoản miễn phí để lưu tỉnh và bộ số yêu thích.",
                   crumbs=[("/", "Trang chủ"), ("/dang-ky", "Tạo tài khoản")], noindex=True, mode="register", max_age=3600)


@router.get("/tai-khoan", response_class=HTMLResponse)
async def account_page(request: Request):
    async with request.app.state.pool.connection() as conn:
        provs = await (await conn.execute("SELECT code, name, region_code FROM provinces WHERE active ORDER BY region_code, name")).fetchall()
    return _render(request, "user_account.html", title="Trang của tôi | LuckyVision", description="Tỉnh và bộ số yêu thích của bạn.",
                   crumbs=[("/", "Trang chủ"), ("/tai-khoan", "Trang của tôi")], noindex=True, provs=provs,
                   games=[x for x in GAMES.values() if x.kind == "pick" and x.code not in ("keno",)], max_age=0)



# ===================== Liên hệ =====================
@router.get("/lien-he", response_class=HTMLResponse)
async def contact_page(request: Request, chu_de: str = Query("", alias="chu-de"), email: str = ""):
    from ..api.contact import TOPICS
    return _render(request, "contact.html", title="Liên hệ | LuckyVision",
                   description="Gửi câu hỏi, báo sai kết quả, góp ý hoặc đề nghị hợp tác với LuckyVision.",
                   crumbs=[("/", "Trang chủ"), ("/lien-he", "Liên hệ")], topics=TOPICS, topic=chu_de if chu_de in TOPICS else "",
                   email=email[:254], support_contact=request.app.state.settings.support_contact, max_age=3600)
