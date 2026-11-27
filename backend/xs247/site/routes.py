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
NAV = [("/", "Kết quả", "kq"), ("/vietlott", "Vietlott", "vl"), ("/thong-ke-phan-tich.html", "Thống kê", "tk"),
       ("/choi-thu.html", "Chơi thử", "ct"), ("/do-ve-anh.html", "Dò vé", "dv"),
       ("/cong-cu/#may-thoi-gian", "Tiện ích", "cc")]
# Mục có nhãn "HOT" trên menu chính
NAV_HOT = {"/do-ve-anh.html", "/choi-thu.html", "/thong-ke-phan-tich.html"}
SUBNAV = {
    "kq": [("/xsmb", "XSMB", "mb"), ("/xsmn", "XSMN", "mn"), ("/xsmt", "XSMT", "mt"), ("/vietlott", "Vietlott", "vietlott"),
           ("/xs-dien-toan", "Điện toán", "dientoan"), ("/so-ket-qua-xsmb-30-ngay", "Sổ kết quả", "so"), ("/live.html", "Trực tiếp", "live"), ("/lich-quay-xo-so", "Lịch quay", "lich"),
           ("/luat-choi", "Luật chơi", "luat"), ("/tin-tuc", "Tin tức", "tintuc")],
    "tk": [("/thong-ke-phan-tich.html", "Tổng quan", "tq"), ("/thong-ke-xsmb", "Miền Bắc", "mb"), ("/thong-ke-xsmn", "Miền Nam", "mn"), ("/thong-ke-xsmt", "Miền Trung", "mt"),
           ("/thong-ke-vietlott-power-655", "Vietlott", "vl-tk"),
           ("/so-sanh", "So sánh số", "ss")],
    "vl": [("/vietlott", "Tổng quan", "vietlott"), ("/vietlott-power-655", "Power 6/55", "power655"),
           ("/vietlott-mega-645", "Mega 6/45", "mega645"), ("/vietlott-lotto-535", "Lotto 5/35", "lotto535"),
           ("/vietlott-keno", "Keno", "keno"), ("/vietlott-max-3d", "Max 3D", "max3d"),
           ("/vietlott-max-3d-pro", "Max 3D Pro", "max3dpro"), ("/vietlott-bingo18", "Bingo18", "bingo18"),
           ("/luat-choi#vietlott", "Luật chơi", "luat"),
           ("/thong-ke-vietlott-power-655", "Thống kê", "vl-tk")],
}
GAME_BY_SLUG = {g.slug: g for g in GAMES.values()}


def _jsonld(site: str, crumbs: list[tuple[str, str]], extra: list[dict] | None = None) -> str:
    graph = [{"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": site + href} for i, (href, name) in enumerate(crumbs)]}]
    graph += extra or []
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")


def _subnav(section: str, sub_active: str | None) -> list[tuple[str, str, str]]:
    """Menu con; ở mục Vietlott, "Thống kê" trỏ tới thống kê của đúng trò đang xem."""
    items = SUBNAV.get(section, [])
    g = GAMES.get(sub_active or "")
    if section == "vl" and g and g.code in STATS_GAMES:
        items = [(f"/thong-ke-{g.slug}", label, key) if key == "vl-tk" else (href, label, key) for href, label, key in items]
    return items


def _render(request: Request, tpl: str, *, title: str, description: str, crumbs: list[tuple[str, str]],
            active: str | None = None, max_age: int = 60, status: int = 200, extra_ld: list[dict] | None = None, **kw) -> HTMLResponse:
    s = request.app.state.settings
    site = s.site_url.rstrip("/")
    path = request.url.path
    if path.startswith("/thong-ke-vietlott"):  # thống kê Vietlott nằm trong mục Thống kê, cạnh 3 miền
        section, sub_active = "tk", "vl-tk"
    elif path.startswith("/vietlott"):
        section = "vl"
        if path.startswith("/thong-ke-vietlott"):
            sub_active = "vl-tk"
        else:
            seg = path.strip("/").split("/")[0]
            g = next((g for slug, g in sorted(GAME_BY_SLUG.items(), key=lambda x: -len(x[0]))
                      if slug.startswith("vietlott") and (seg == slug or seg.startswith(slug + "-"))), None)
            sub_active = g.code if g else "vietlott"
    else:
        section = "tk" if path.startswith(("/thong-ke", "/so-sanh")) else "kq"
        sub_active = ("so" if path.startswith("/so-ket-qua") else "lich" if path.startswith("/lich-quay") else "luat" if path.startswith("/luat-choi")
                      else "tintuc" if path.startswith("/tin-tuc") else "ss" if path.startswith("/so-sanh") else active)
    ctx = {"title": title, "description": description, "canonical": site + path, "site_url": site,
           "site_name": s.site_name, "contact_phone": s.contact_phone,
           "contact_tel": "".join(ch for ch in s.contact_phone if ch.isdigit() or ch == "+"), "contact_email": s.contact_email, "nav": NAV, "nav_hot": NAV_HOT, "section": section, "subnav": _subnav(section, sub_active), "sub_active": sub_active,
           "active": active, "breadcrumbs": crumbs if len(crumbs) > 1 else None,
           "jsonld": _jsonld(site, crumbs, extra_ld), "short": D.PRIZE_SHORT, **kw}
    resp = templates.TemplateResponse(request, tpl, ctx, status_code=status)
    resp.headers["Cache-Control"] = f"public, max-age={max_age}, stale-while-revalidate=600"
    return resp


def _not_found(request: Request, message: str) -> HTMLResponse:
    return _render(request, "notfound.html", title="Không tìm thấy trang | XS247", description=message,
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
                             "when": f"{D.weekday(day)} {D.dmy(day)}" if day else "", "draws": draws, "display": D.DISPLAY[r],
                             "snap": await D.region_snapshot(conn, r)})
        for g in GAMES.values():
            if g.code not in ("power655", "mega645"):
                continue
            ds = await D.game_draws(conn, g.code, limit=1)
            games.append({"slug": g.slug, "name": g.name, "draw": ds[0] if ds else None, "g": g,
                          "when": f"{D.weekday(ds[0]['draw_date'])} {D.dmy(ds[0]['draw_date'])}" if ds else ""})
        try:  # bảng tin tức thiếu hoặc lỗi không được làm hỏng trang chủ
            news, _total = await D.news_list(conn, 5, 0)
        except Exception:
            news = []
    s = request.app.state.settings
    site = s.site_url.rstrip("/")
    digits = "".join(ch for ch in s.contact_phone if ch.isdigit())
    intl = "+84" + digits[1:] if digits.startswith("0") else ("+" + digits if digits else "")
    org = {"@type": "WebSite", "name": s.site_name, "url": site + "/", "inLanguage": "vi-VN"}
    organization = {"@type": "Organization", "name": s.site_name, "url": site, "logo": site + "/icons/icon-512.png",
                    "contactPoint": {"@type": "ContactPoint", "telephone": intl, "email": s.contact_email,
                                     "contactType": "customer support", "areaServed": "VN", "availableLanguage": "vi"}}
    return _render(request, "home.html", title="Kết quả xổ số hôm nay XSMB, XSMN, XSMT, Vietlott | XS247",
                   description="Kết quả xổ số miền Bắc, miền Nam, miền Trung, Vietlott Power 6/55, Mega 6/45 hôm nay, đối chiếu nhiều nguồn; thống kê lô gan, sổ kết quả và phân tích số liệu minh bạch.",
                   crumbs=[("/", "Trang chủ")], extra_ld=[org, organization], sections=sections, games=games, news=news)


# ---------------- kết quả theo miền và ngày ----------------
async def _region_day(request: Request, region: str, day: date | None, is_latest: bool):
    slug = D.REGION_SLUG[region]
    async with request.app.state.pool.connection() as conn:
        latest = await D.latest_day(conn, region)
        day = day or latest
        if not day:
            # Trang miền có trong menu: khi chưa có dữ liệu vẫn trả 200 với thông báo thân thiện (không 404, không lập chỉ mục)
            name = D.REGION_NAMES[region]
            msg = f"Chưa có kết quả xổ số {name}. Kết quả sẽ hiển thị ngay sau kỳ quay đầu tiên được cập nhật."
            return _render(request, "notfound.html", title=f"{slug.upper()} hôm nay: kết quả xổ số {name} | XS247",
                           description=msg, crumbs=[("/", "Trang chủ"), (f"/{slug}", slug.upper())], noindex=True,
                           message=msg, heading=f"{slug.upper()}: kết quả xổ số {name}", max_age=60)
        draws = await D.day_draws(conn, region, day)
        prev, nxt = await D.neighbour_days(conn, region, day)
    if not draws:
        return _not_found(request, f"Không có kết quả xổ số {D.REGION_NAMES[region]} ngày {D.dmy(day)}. Có thể ngày này không quay hoặc chưa có kết quả.")
    code = slug.upper()
    h1 = f"{code} {D.dmy(day)}: kết quả xổ số {D.REGION_NAMES[region]} {D.weekday(day).lower()}"
    title = (f"{code} hôm nay {D.dmy(day)}, kết quả xổ số {D.REGION_NAMES[region]}" if is_latest
             else f"{code} {D.dmy(day)}, kết quả xổ số {D.REGION_NAMES[region]} {D.weekday(day)}") + " | XS247"
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
    return _render(request, "province.html", title=f"Xổ số {p['name']}: kết quả mới nhất, các kỳ trước | XS247",
                   description=f"Kết quả xổ số {p['name']} mới nhất và 10 kỳ gần đây; lịch quay {days}; thống kê lô gan {p['name']}.",
                   crumbs=[("/", "Trang chủ"), (f"/{D.REGION_SLUG[region]}", f"Xổ số {D.REGION_NAMES[region]}"), (f"/xs-{code}", p["name"])],
                   active=region, region=region, slug=D.REGION_SLUG[region], region_name=D.REGION_NAMES[region], code=code, pname=p["name"],
                   h1=f"Xổ số {p['name']}", summary=summary, draws=draws, display=D.DISPLAY[region],
                   latest_label=f"{D.weekday(draws[0]['draw_date'])} {D.dmy(draws[0]['draw_date'])}" if draws else "", max_age=300)


# ---------------- Vietlott ----------------
STATS_GAMES = ("power655", "mega645", "lotto535", "keno", "max3d", "max3dpro", "bingo18")   # có trang /thong-ke-<slug>
TIME_MACHINE_GAMES = ("power655", "mega645", "lotto535", "max3d", "max3dpro")  # Máy thời gian trong Công cụ
PLAY_GAMES = ("power655", "mega645")            # có Chơi thử
GENERATOR_GAMES = ("power655",)                 # Tạo bộ số trong Công cụ chỉ có Power 6/55


def _next_info(g, at, latest: dict | None, gap: int | None = 1) -> dict:
    """Thông tin kỳ quay kế tiếp để hiển thị; at là giờ Việt Nam hoặc None nếu không tính được.
    gap: số kỳ theo lịch từ kỳ mới nhất có dữ liệu đến kỳ kế tiếp (đúng cả khi thiếu dữ liệu vài kỳ)."""
    if not at:
        return {"iso": None, "text": g.schedule, "seq": None, "when": ""}
    seq = None
    if not g.multi_daily and gap and latest and latest.get("draw_seq") and latest["draw_date"] < at.date():
        seq = f"{latest['draw_seq'] + gap:0{g.seq_width}d}"
    return {"iso": at.isoformat(), "text": g.schedule, "seq": seq,
            "when": f"{D.weekday(at.date())} {D.dmy(at.date())} lúc {at:%H:%M}", "time": f"{at:%H:%M}"}


def _quick_links(g) -> list[dict]:
    links = []
    if g.code in STATS_GAMES:
        links.append({"href": f"/thong-ke-{g.slug}", "name": "Thống kê", "desc": "Số ra nhiều, số lâu chưa ra, cặp số đi cùng nhau."})
    if g.code in TIME_MACHINE_GAMES:
        tool = "power655" if g.code == "power655" else g.code   # công cụ Vietlott có đường dẫn riêng theo trò
        links.append({"href": f"/cong-cu/#{tool}-may-thoi-gian", "name": "Máy thời gian", "desc": "Nếu chơi một bộ số từ trước đến nay, lời hay lỗ?"})
    links.append({"href": "/do-ve-anh.html", "name": "Dò vé", "desc": "Nhập số hoặc chụp ảnh vé để biết trúng gì."})
    if g.code in GENERATOR_GAMES:
        links.append({"href": "/cong-cu/#power655-tao-so", "name": "Tạo bộ số", "desc": "Chọn ngẫu nhiên có bộ lọc."})
    if g.code in PLAY_GAMES:
        links.append({"href": "/choi-thu.html", "name": "Chơi thử", "desc": "Chơi thử bằng điểm ảo, không dùng tiền thật."})
    return links


async def _game_page(request: Request, g, day: date | None):
    async with request.app.state.pool.connection() as conn:
        recent = await D.game_draws(conn, g.code, limit=30 if g.multi_daily else 20)
        day_draws = await D.game_draws(conn, g.code, day=day) if day else []
        nxt, gap = {}, None
        if not day and g.family == "vietlott":
            try:
                nxt = await D.next_draws(conn, games=[g.code])
                gap = (await D.scheduled_count(conn, g.code, recent[0]["draw_date"], nxt[g.code].date())
                       if recent and g.code in nxt and not g.multi_daily else None)
            except Exception:  # lịch lỗi không được làm hỏng trang kết quả
                nxt, gap = {}, None
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
    return _render(request, "game.html", title=f"{g.name}{when}: kết quả, các kỳ trước | XS247",
                   description=f"Kết quả {g.name}{when}. {summary} " + (g.schedule + ". " if g.schedule else "") + "Xem các kỳ trước và thống kê.",
                   crumbs=crumbs, active=g.family, region=g.code, g=g, h1=f"Kết quả {g.name}{when}", summary=summary, main=main,
                   day_draws=day_draws if (day and g.multi_daily) else [], recent=[] if day else recent, slug=g.slug, odds_text=odds,
                   hero=(not day and g.family == "vietlott"), next_info=_next_info(g, nxt.get(g.code), recent[0] if recent else None, gap if (not day and g.family == "vietlott") else None),
                   quick_links=_quick_links(g),
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
        nxt = {}
        if family == "vietlott":
            try:
                nxt = await D.next_draws(conn)
            except Exception:
                nxt = {}
        for g in GAMES.values():
            if g.family != family:
                continue
            ds = await D.game_draws(conn, g.code, limit=1)
            gap = None
            if ds and g.code in nxt and not g.multi_daily:
                try:
                    gap = await D.scheduled_count(conn, g.code, ds[0]["draw_date"], nxt[g.code].date())
                except Exception:
                    gap = None
            items.append({"g": g, "d": ds[0] if ds else None, "next": _next_info(g, nxt.get(g.code), ds[0] if ds else None, gap)})
    if family == "vietlott":
        title, h1 = "Kết quả Vietlott hôm nay: Power 6/55, Mega 6/45, Lotto 5/35, Max 3D, Keno, Bingo18 | XS247", "Kết quả Vietlott"
        desc = "Kết quả mới nhất mọi trò chơi Vietlott: Power 6/55, Mega 6/45, Lotto 5/35, Max 3D, Max 3D Pro, Keno, Bingo18, lấy từ trang chính thức."
        lead = "Kết quả mới nhất của tất cả trò chơi Vietlott, lấy từ trang chính thức vietlott.vn."
    else:
        title, h1 = "Xổ số điện toán: 1*2*3, Thần Tài 4, 6x36 | XS247", "Xổ số điện toán miền Bắc"
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
    return _render(request, "so.html", title=f"Sổ kết quả {code} {n} ngày gần nhất | XS247",
                   description=f"Sổ kết quả xổ số {D.REGION_NAMES[region]} {n} ngày: giải đặc biệt, giải nhất và lô tô từng kỳ, in được.",
                   crumbs=[("/", "Trang chủ"), (f"/{slug}", f"Xổ số {D.REGION_NAMES[region]}"), (request.url.path, f"Sổ {n} ngày")],
                   active=region, region=region, slug=slug, days=n, groups=groups, h1=f"Sổ kết quả {code} {n} ngày",
                   summary=f"{len(groups)} ngày quay, {len(draws)} kỳ, mới nhất ở trên cùng.", max_age=600)


# ---------------- thống kê lô gan ----------------
async def _stats_scope(conn, kind: str, current: str | None) -> dict:
    """Thanh "Phạm vi thống kê" dùng chung cho mọi trang thống kê: Loại xổ số + Đài/Trò.
    kind: mb | mn | mt | vl; current: mã đài (mn/mt) hoặc mã trò (vl), None = tất cả đài."""
    kinds = [("mb", "Miền Bắc", "/thong-ke-xsmb"), ("mn", "Miền Nam", "/thong-ke-xsmn"),
             ("mt", "Miền Trung", "/thong-ke-xsmt"), ("vl", "Vietlott", "/thong-ke-vietlott-power-655")]
    if kind == "vl":
        items = [(f"/thong-ke-{g.slug}", g.name.replace("Vietlott ", ""), g.code == current)
                 for g in GAMES.values() if g.code in STATS_GAMES]
        label = "Trò chơi"
    elif kind == "mb":
        items, label = [("/thong-ke-xsmb", "Xổ số miền Bắc", True)], "Đài"
    else:
        provs = await D.provinces_of(conn, kind)
        items = [(f"/thong-ke-{D.REGION_SLUG[kind]}", f"Tất cả đài {D.REGION_NAMES[kind]}", current is None)]
        items += [(f"/thong-ke-xs-{p['code']}", p["name"], p["code"] == current) for p in provs]
        label = "Đài"
    return {"kinds": [(href, name, k == kind) for k, name, href in kinds], "options": items, "label": label}


def _merge_by_day(draws_oldest_first: list[dict]) -> list[dict]:
    """Gộp các đài cùng ngày thành một "ngày quay" (lô tô của mọi đài) để thống kê cả miền."""
    days: dict = {}
    for d in draws_oldest_first:
        days.setdefault(d["draw_date"], {"draw_date": d["draw_date"], "loto": []})["loto"].extend(d["loto"])
    return list(days.values())


async def _stats(request: Request, region: str, code: str | None):
    async with request.app.state.pool.connection() as conn:
        p = await D.province(conn, code) if code else None
        if code and (not p or p["region_code"] != region):
            return _not_found(request, "Không có đài này.")
        scope = await _stats_scope(conn, region, code)
        unit = "kỳ"
        if region == "mb":
            draws = (await D.region_range(conn, "mb", 365))[::-1]
        elif code:
            draws = (await D.province_draws(conn, code, 120))[::-1]
        else:  # cả miền: gộp mọi đài theo ngày quay
            draws, unit = _merge_by_day((await D.region_range(conn, region, 120))[::-1]), "ngày quay"
    slug = D.REGION_SLUG[region]
    name = p["name"] if p else D.REGION_NAMES[region]
    st = D.gan_stats(draws) if draws else None
    if region != "mb" and not code:
        h1 = f"Thống kê lô gan xổ số {name} (tất cả đài)"
        summary = (f"Gộp lô tô của mọi đài {name} theo từng ngày quay, {len(draws)} ngày gần nhất. Chọn một đài ở ô phía trên để xem riêng đài đó."
                   if draws else "Chưa đủ dữ liệu.")
    else:
        h1 = f"Thống kê lô gan {name}"
        summary = f"Phân tích {len(draws)} kỳ quay gần nhất của {name}." if draws else "Chưa đủ dữ liệu."
    path = f"/thong-ke-xs-{code}" if code else f"/thong-ke-{slug}"
    crumbs = [("/", "Trang chủ"), (f"/{slug}", f"Xổ số {D.REGION_NAMES[region]}"), (path, "Thống kê" + (f" {name}" if p else ""))]
    return _render(request, "stats.html", title=f"{h1}: lô lâu chưa về, lô về nhiều | XS247",
                   description=f"Lô gan, lô về nhiều và về ít của {name}, cập nhật sau mỗi kỳ quay. Kèm giải thích trung thực về xác suất.",
                   crumbs=crumbs, active=region, region=region, h1=h1, summary=summary, st=st, scope=scope, unit=unit, current=code, max_age=600)


for _r, _slug in D.REGION_SLUG.items():
    def _make_s(region=_r, slug=_slug):
        async def page(request: Request):
            return await _stats(request, region, None)
        router.add_api_route(f"/thong-ke-{slug}", page, response_class=HTMLResponse, include_in_schema=False)
    _make_s()


def _vl_picker(g) -> list[tuple[str, str, bool]]:
    """Ô chọn trò trên trang thống kê Vietlott: (đường dẫn, tên, đang chọn)."""
    return [(f"/thong-ke-{x.slug}", x.name.replace("Vietlott ", ""), x.code == g.code)
            for x in GAMES.values() if x.code in STATS_GAMES]


async def stats_other(request: Request, g):
    """Thống kê Max 3D / Max 3D Pro (số 3 chữ số) và Bingo18 (3 viên xúc xắc): chỉ mô tả quá khứ."""
    async with request.app.state.pool.connection() as conn:
        draws = (await D.game_draws(conn, g.code, limit=300))[::-1]
        scope = await _stats_scope(conn, "vl", g.code)
    n, ctx = len(draws), {}
    if g.kind == "dice":
        sums = {k: 0 for k in range(3, 19)}
        faces = {k: 0 for k in range(1, 7)}
        for d in draws:
            vals = [int(x) for x in d["prizes"].get("main", [])][:3]
            if len(vals) == 3:
                sums[sum(vals)] += 1
                for v in vals:
                    faces[v] += 1
        ctx = {"bars": [(str(k), c) for k, c in sums.items()], "bars_title": "Phân bố tổng điểm 3 viên xúc xắc",
               "bars2": [(str(k), c) for k, c in faces.items()], "bars2_title": "Số lần ra của từng mặt xúc xắc",
               "note": "Tổng 10 và 11 có nhiều cách ra nhất (27/216 mỗi tổng), tổng 3 và 18 chỉ có 1 cách (1/216)."}
    else:
        counts: dict[str, int] = {}
        last_digit = {k: 0 for k in range(10)}
        for d in draws:
            for nums in d["prizes"].values():
                for x in nums:
                    counts[x] = counts.get(x, 0) + 1
                    last_digit[int(x[-1])] += 1
        hot = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:12]
        ctx = {"bars": [(str(k), c) for k, c in last_digit.items()], "bars_title": "Tần suất chữ số cuối của các số trúng",
               "hot": hot, "note": "Mỗi kỳ có 20 số 3 chữ số trúng thưởng trong 1.000 số có thể; số nào cũng có cơ hội như nhau."}
    for key in ("bars", "bars2"):
        if key in ctx:
            ctx[key + "_max"] = max((c for _, c in ctx[key]), default=0) or 1
    return _render(request, "stats_other.html", title=f"Thống kê {g.name}: tần suất kết quả | XS247",
                   description=f"Thống kê kết quả {g.name} trong {n} kỳ gần nhất: chỉ mô tả quá khứ, mỗi kỳ là ngẫu nhiên.",
                   crumbs=[("/", "Trang chủ"), (f"/{g.slug}", g.name.replace("Vietlott ", "")), (f"/thong-ke-{g.slug}", "Thống kê")],
                   active=g.code, region=g.code, g=g, h1=f"Thống kê {g.name}", draws=n, scope=scope, max_age=600, **ctx)


async def stats_game(request: Request, g):
    async with request.app.state.pool.connection() as conn:
        draws = (await D.game_draws(conn, g.code, limit=300))[::-1]
        scope = await _stats_scope(conn, "vl", g.code)
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
    mx = max(rf.values(), default=0) or 1  # chưa có kỳ nào: tránh chia cho 0
    return _render(request, "stats_pick.html", title=f"Thống kê {g.name}: số về nhiều, số lâu chưa về | XS247",
                   description=f"Tần suất từng số {g.name} trong {len(recent)} kỳ gần nhất, số lâu chưa về, kèm xác suất lý thuyết {theory:.1%} mỗi số.",
                   crumbs=[("/", "Trang chủ"), (f"/{g.slug}", g.name.replace("Vietlott ", "")), (f"/thong-ke-{g.slug}", "Thống kê")],
                   active=g.code, region=g.code, g=g, h1=f"Thống kê {g.name}", draws=n, recent=len(recent), rf=rf, mx=mx,
                   gan=gan, hot=hot, cold=cold, theory=theory, expected=expected, scope=scope, max_age=600)


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


@router.get("/nav.js")
async def nav_js():
    """Menu dùng chung cho các trang tĩnh (Thống kê, Chơi thử, Dò vé, Trực tiếp, Công cụ), sinh từ cùng NAV/SUBNAV
    với trang máy chủ để menu ở mọi trang luôn giống nhau. Trang tĩnh đặt
    <header class="top" id="lvHeader" data-section="tk" data-sub="tq"></header><script src="/nav.js"></script>;
    các phần tử con có data-keep (ví dụ nút của trang Trực tiếp) được giữ lại trong thanh đầu trang."""
    data = json.dumps({"nav": NAV, "sub": SUBNAV, "hot": sorted(NAV_HOT)}, ensure_ascii=False).replace("</", r"<\/")
    js = NAV_JS.replace("__DATA__", data)
    return Response(js, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-cache"})


NAV_JS = r"""(function () {
  var D = __DATA__, h = document.getElementById('lvHeader'); if (!h) return;
  var sec = h.getAttribute('data-section') || '', sub = h.getAttribute('data-sub') || '';
  var esc = function (t) { return String(t).replace(/[&<>"]/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); };
  var keep = Array.prototype.slice.call(h.querySelectorAll('[data-keep]'));
  var main = D.nav.map(function (n) {
    var label = esc(n[1]).replace(' 6/55', '<span class="hide-m"> 6/55</span>') + ((D.hot || []).indexOf(n[0]) >= 0 ? '<span class="hot" aria-hidden="true">HOT</span>' : '');
    return '<a href="' + esc(n[0]) + '"' + (n[2] === sec ? ' aria-current="page"' : '') + '>' + label + '</a>';
  }).join('');
  var items = D.sub[sec] || [];
  var subHtml = items.length ? '<nav class="sub" aria-label="Mục con">' + items.map(function (n) {
    return '<a href="' + esc(n[0]) + '"' + (n[2] === sub ? ' aria-current="true"' : '') + '>' + esc(n[1]) + '</a>';
  }).join('') + '</nav>' : '';
  h.innerHTML = '<div class="in"><a class="brand" href="/" aria-label="XS247 - trang chủ"><span class="brand-ball" aria-hidden="true">X<i class="brand-dot"></i></span><span class="brand-name">XS<b class="brand-live">247</b></span></a>' +
    '<form class="search" action="/tim-kiem" method="get" role="search"><label class="sr" for="q">Tìm kiếm</label>' +
    '<input id="q" name="q" placeholder="Tìm: xsmn 26/10, lô 27, power kỳ 1417…" autocomplete="off"></form>' +
    '<a class="acct" id="acct" href="/dang-nhap">Đăng nhập</a><nav class="main" aria-label="Mục chính">' + main + '</nav></div>' + subHtml;
  var inner = h.querySelector('.in'); keep.forEach(function (k) { inner.appendChild(k); });
})();
"""


@router.get("/robots.txt")
async def robots(request: Request):
    site = request.app.state.settings.site_url.rstrip("/")
    txt = "User-agent: *\nAllow: /\nDisallow: /v1/\nDisallow: /admin.html\nDisallow: /chon-ngay\n\nSitemap: " + site + "/sitemap.xml\n"
    return PlainTextResponse(txt, headers={"Cache-Control": "public, max-age=86400"})


# Đường dẫn chung đặt cuối cùng để không che các trang trò chơi (vd. /xs-dien-toan-123, /xs-than-tai-4)
for _slug, _fn in sorted(_GAME_DAY_ROUTES, key=lambda x: -len(x[0])):
    router.add_api_route(f"/{_slug}-{{ds}}", _fn, response_class=HTMLResponse, include_in_schema=False)
for _g in (GAMES[c] for c in STATS_GAMES):
    def _make_st(g=_g):
        async def page(request: Request):
            return await (stats_game(request, g) if g.kind == "pick" else stats_other(request, g))
        router.add_api_route(f"/thong-ke-{g.slug}", page, response_class=HTMLResponse, include_in_schema=False)
    _make_st()
router.add_api_route("/thong-ke-xs-{code}", stats_province, response_class=HTMLResponse, include_in_schema=False)
router.add_api_route("/xs-{code}", province_page, response_class=HTMLResponse, include_in_schema=False)


# ===================== Lịch mở thưởng =====================
async def _week_schedule(request: Request):
    """(lịch theo thứ {1..7: {mn, mt, mb: [đài]}}, giờ quay từng miền, thứ hôm nay theo giờ Việt Nam)."""
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
    return week, times, _dt.now(VN_TZ).isoweekday()


@router.get("/lich-quay-xo-so", response_class=HTMLResponse)
async def schedule_page(request: Request):
    week, times, today = await _week_schedule(request)
    vl =[g for g in GAMES.values() if g.family == "vietlott"]
    faq = [("Xổ số miền Nam quay lúc mấy giờ?", f"Xổ số miền Nam quay lúc {times.get('mn', '16:15')} hằng ngày, mỗi ngày 3–4 đài."),
           ("Xổ số miền Trung quay lúc mấy giờ?", f"Xổ số miền Trung quay lúc {times.get('mt', '17:15')} hằng ngày, mỗi ngày 2–3 đài."),
           ("Xổ số miền Bắc quay lúc mấy giờ?", f"Xổ số miền Bắc quay lúc {times.get('mb', '18:15')} tất cả các ngày trong tuần."),
           ("Vietlott Power 6/55 quay vào ngày nào?", "Power 6/55 quay thứ Ba, thứ Năm và thứ Bảy lúc 18:00; Mega 6/45 quay thứ Tư, thứ Sáu và Chủ nhật lúc 18:00.")]
    ld = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return _render(request, "schedule.html", title="Lịch quay xổ số ba miền và Vietlott trong tuần | XS247",
                   description="Lịch mở thưởng xổ số miền Nam, miền Trung, miền Bắc theo từng ngày trong tuần, giờ quay và lịch các trò chơi Vietlott.",
                   crumbs=[("/", "Trang chủ"), ("/lich-quay-xo-so", "Lịch quay xổ số")], active=None, extra_ld=ld,
                   week=week, times=times, today=today, vl=vl, faq=faq, max_age=3600)


# ===================== Luật chơi =====================
@router.get("/luat-choi", response_class=HTMLResponse)
async def rules_page(request: Request):
    from ..domain import rules as R
    week, times, today = await _week_schedule(request)
    # giờ quay 3 miền lấy từ lịch trong CSDL; dùng bản sao để không sửa dữ liệu tĩnh
    games = [dict(g, time=times.get(g["region"], g["time"])) if g["region"] else g for g in R.RULES]
    faq = [("Vé số trúng thưởng thế nào?", "Dò dãy số trên vé với kết quả của kỳ quay: xổ số kiến thiết dò theo số chữ số cuối của từng giải, Vietlott dò theo số lượng số trùng."),
           ("Thuế khi trúng thưởng là bao nhiêu?", R.CLAIM["tax"]),
           ("Hạn lĩnh thưởng Vietlott là bao lâu?", R.CLAIM["vietlott"][0]),
           ("Trúng nhiều giải có được lĩnh tất cả không?", "Xổ số kiến thiết, Max 3D và Max 3D Pro được lĩnh tổng các giải trúng; Power 6/55, Mega 6/45 và Lotto 5/35 chỉ lĩnh hạng giải cao nhất.")]
    ld = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]
    return _render(request, "rules.html", title="Luật chơi xổ số 3 miền và Vietlott: cách trúng, giờ quay, giá trị giải | XS247",
                   description="Luật chơi, giờ quay, điều kiện trúng và giá trị giải của xổ số ba miền, Power 6/55, Mega 6/45, Lotto 5/35, Max 3D, Keno, Bingo18; hạn lĩnh thưởng và thuế.",
                   crumbs=[("/", "Trang chủ"), ("/luat-choi", "Luật chơi")], active="luat", extra_ld=ld,
                   games=games, week=week, today=today, faq=faq, R=R, max_age=3600)


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
    title = (f"So sánh {' và '.join(fmt(x) for x in nums)}, {scope_name}" if nums else "So sánh các con số") + " | XS247"
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
    return _render(request, "search.html", title=(f"Tìm “{q}”" if q else "Tìm kiếm") + " | XS247",
                   description="Tìm nhanh kết quả xổ số theo ngày, theo đài, theo kỳ Vietlott, dò vé và so sánh số.",
                   crumbs=[("/", "Trang chủ"), ("/tim-kiem", "Tìm kiếm")], active=None, noindex=True, q=q, answers=answers, note=note, max_age=60)


# ===================== Tài khoản người dùng (giao diện) =====================
@router.get("/dang-nhap", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "user_login.html", title="Đăng nhập | XS247", description="Đăng nhập để lưu tỉnh và bộ số yêu thích.",
                   crumbs=[("/", "Trang chủ"), ("/dang-nhap", "Đăng nhập")], noindex=True, mode="login", max_age=3600,
                   support_contact=request.app.state.settings.support_contact)


@router.get("/dang-ky", response_class=HTMLResponse)
async def register_page(request: Request):
    return _render(request, "user_login.html", title="Tạo tài khoản | XS247", description="Tạo tài khoản miễn phí để lưu tỉnh và bộ số yêu thích.",
                   crumbs=[("/", "Trang chủ"), ("/dang-ky", "Tạo tài khoản")], noindex=True, mode="register", max_age=3600)


@router.get("/tai-khoan", response_class=HTMLResponse)
async def account_page(request: Request):
    async with request.app.state.pool.connection() as conn:
        provs = await (await conn.execute("SELECT code, name, region_code FROM provinces WHERE active ORDER BY region_code, name")).fetchall()
    return _render(request, "user_account.html", title="Trang của tôi | XS247", description="Tỉnh và bộ số yêu thích của bạn.",
                   crumbs=[("/", "Trang chủ"), ("/tai-khoan", "Trang của tôi")], noindex=True, provs=provs,
                   games=[x for x in GAMES.values() if x.kind == "pick" and x.code not in ("keno",)], max_age=0)



# ===================== Tin tức =====================
NEWS_PAGE = 20
NEWS_CATS = [("", "Tất cả"), ("ket-qua", "Kết quả"), ("vietlott", "Vietlott"), ("thong-ke", "Thống kê"), ("bao-chi", "Báo chí")]


def _news_time(t) -> str:
    """dd/mm/yyyy HH:MM theo giờ Việt Nam."""
    from datetime import datetime as _dt
    from ..config import VN_TZ
    if not isinstance(t, _dt):
        return D.dmy(t) if isinstance(t, date) else ""
    return (t.astimezone(VN_TZ) if t.tzinfo else t).strftime("%d/%m/%Y %H:%M")


def _iso(t) -> str:
    from datetime import datetime as _dt
    from ..config import VN_TZ
    if isinstance(t, _dt):
        return (t.astimezone(VN_TZ) if t.tzinfo else t.replace(tzinfo=VN_TZ)).isoformat()
    return t.isoformat() if isinstance(t, date) else ""


templates.env.globals.update(news_time=_news_time, news_topic_label=D.NEWS_TOPIC_LABEL)


@router.get("/tin-tuc", response_class=HTMLResponse)
async def news_index(request: Request, trang: int = 1, muc: str = ""):
    page = max(1, min(trang, 10000))
    muc = muc if muc in D.NEWS_TOPICS else ""
    async with request.app.state.pool.connection() as conn:
        items, total = await D.news_list(conn, NEWS_PAGE, (page - 1) * NEWS_PAGE, D.NEWS_TOPICS.get(muc))
    pages = max(1, -(-total // NEWS_PAGE))
    q = f"muc={muc}&" if muc else ""

    def url(p: int) -> str:
        return "/tin-tuc" + (f"?{q}trang={p}" if p > 1 else (f"?muc={muc}" if muc else ""))
    return _render(request, "news_list.html", title="Tin tức xổ số: kết quả mới, thống kê tuần, Vietlott | XS247",
                   description="Tin tức xổ số: tổng hợp kết quả theo ngày, kỳ quay Vietlott, thống kê tuần từ số liệu đã công bố và liên kết bài của các báo.",
                   crumbs=[("/", "Trang chủ"), ("/tin-tuc", "Tin tức")], active="tintuc", noindex=(page > 1 or bool(muc)),
                   items=items, total=total, page=page, pages=pages, muc=muc, cats=NEWS_CATS,
                   prev_url=url(page - 1) if page > 1 else None, next_url=url(page + 1) if page < pages else None,
                   cat_url=lambda m: "/tin-tuc" + (f"?muc={m}" if m else ""), max_age=120)


@router.get("/tin-tuc/{slug}", response_class=HTMLResponse)
async def news_article(request: Request, slug: str):
    async with request.app.state.pool.connection() as conn:
        a = await D.news_by_slug(conn, slug)
        if not a:
            return _not_found(request, "Không tìm thấy bài viết này. Bài có thể đã được gỡ.")
        try:
            related, _t = await D.news_list(conn, 6, 0)
        except Exception:
            related = []
    related = [r for r in related if r["id"] != a["id"]][:5]
    s = request.app.state.settings
    body = a.get("body") if isinstance(a.get("body"), dict) else {}
    desc = (a.get("summary") or a["title"])[:300]
    ld = {"@type": "NewsArticle", "headline": a["title"][:110], "datePublished": _iso(a["published_at"]),
          "dateModified": _iso(a.get("updated_at") or a["published_at"]), "description": desc,
          "mainEntityOfPage": s.site_url.rstrip("/") + request.url.path, "inLanguage": "vi-VN",
          "publisher": {"@type": "Organization", "name": s.site_name}}
    return _render(request, "news_article.html", title=f"{a['title']} | XS247", description=desc,
                   crumbs=[("/", "Trang chủ"), ("/tin-tuc", "Tin tức"), (request.url.path, a["title"])], active="tintuc",
                   extra_ld=[ld], a=a, body=body, related=related, max_age=300)


@router.get("/lien-he", response_class=HTMLResponse)
async def contact_page(request: Request, chu_de: str = Query("", alias="chu-de"), email: str = ""):
    from ..api.contact import TOPICS
    return _render(request, "contact.html", title="Liên hệ | XS247",
                   description="Gửi câu hỏi, báo sai kết quả, góp ý hoặc đề nghị hợp tác với XS247.",
                   crumbs=[("/", "Trang chủ"), ("/lien-he", "Liên hệ")], topics=TOPICS, topic=chu_de if chu_de in TOPICS else "",
                   email=email[:254], support_contact=request.app.state.settings.support_contact, max_age=3600)
