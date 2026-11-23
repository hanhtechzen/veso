import ast
import re
from datetime import date
from pathlib import Path

from luckyvision.notify import format_message
from luckyvision.site.data import gan_stats, parse_slug_date, slug_date
from luckyvision.site.routes import _jsonld, _summary


def test_slug_dates():
    assert slug_date(date(2026, 10, 29)) == "29-10-2026"
    assert parse_slug_date("29-10-2026") == date(2026, 10, 29)
    assert parse_slug_date("31-02-2026") is None and parse_slug_date("abc") is None


def test_summary_and_gan():
    draws = [{"pname": "TP. HCM", "prizes": {"db": ["472899"]}, "loto": [87, 87, 5, 7]},
             {"pname": "Cà Mau", "prizes": {"db": ["929097"]}, "loto": [87, 5, 99]}]
    s = _summary("mn", draws)
    assert "TP. HCM 472899" in s and "87 (3 lần)" in s and "Đầu 1" in s
    st = gan_stats([{"loto": [1, 2]}, {"loto": [2]}, {"loto": [3]}], top=100)
    gan = dict(st["gan"])
    assert gan[0] == 3 and gan[1] == 2 and gan[2] == 1 and gan[3] == 0


def test_jsonld_escapes_script_end():
    ld = _jsonld("https://x.vn", [("/", "Trang chủ"), ("/xsmb", "</script>")])
    assert "</script>" not in ld and "<\\/script>" in ld


# ---- Quy định: không công khai "dự báo/dự đoán" ----
SITE = Path(__file__).resolve().parents[1] / "luckyvision" / "site"
FORBIDDEN = re.compile(r"dự\s*báo|dự\s*đoán|du-doan", re.IGNORECASE)


def test_nav_has_no_prediction_link_or_label_and_has_statistics_analysis():
    from luckyvision.site.routes import NAV
    for href, label, _ in NAV:
        assert "du-doan" not in href and not FORBIDDEN.search(label), (href, label)
    pairs = [(h, l) for h, l, _ in NAV]
    assert ("/thong-ke-phan-tich.html", "Thống kê") in pairs
    assert ("/choi-thu.html", "Chơi thử") in pairs
    assert [p for p in pairs if "thong-ke" in p[0]] == [("/thong-ke-phan-tich.html", "Thống kê")]
    assert all(l != "Thống kê phân tích" and h != "/thong-ke-xsmb" for h, l in pairs)


def test_head_tail_counts_first_and_last_digit():
    from luckyvision.site.data import head_tail
    ht = head_tail(["05", "15", "99", "00"])
    assert ht["dau"] == {0: 2, 1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 1}
    assert ht["duoi"] == {0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 2, 6: 0, 7: 0, 8: 0, 9: 1}
    empty = head_tail([])
    assert empty["dau"] == {i: 0 for i in range(10)} and empty["duoi"] == {i: 0 for i in range(10)}


def test_number_stats_gan_and_counts():
    from luckyvision.site.personal import number_stats
    today = date(2026, 11, 5)
    draws = [(date(2026, 7, 1), ["05", "77"]),
             (date(2026, 11, 4), ["05", "05", "10"]),   # 05 xuất hiện 2 lần trong một kỳ
             (date(2026, 10, 10), ["05"]),               # cách 26 ngày
             (date(2026, 11, 5), ["10"])]                # hôm nay: tính cả
    out = number_stats(draws, ["05", "77", "33", "10"], today)
    assert [o["number"] for o in out] == ["05", "77", "33", "10"]
    n05, n77, n33, n10 = out
    assert (n05["last_date"], n05["gan_days"], n05["count30"], n05["count90"]) == (date(2026, 11, 4), 1, 3, 3)
    assert (n77["last_date"], n77["gan_days"], n77["count30"], n77["count90"]) == (date(2026, 7, 1), 127, 0, 0)
    assert (n33["last_date"], n33["gan_days"], n33["count30"], n33["count90"]) == (None, None, 0, 0)
    assert (n10["last_date"], n10["gan_days"], n10["count30"], n10["count90"]) == (today, 0, 2, 2)


def test_subnav_has_no_prediction_links_or_admin_only_tools():
    from luckyvision.site.routes import SUBNAV
    for items in SUBNAV.values():
        for href, label, _ in items:
            assert "du-doan" not in href and not FORBIDDEN.search(label), (href, label)
            for frag in ("#dau-truong", "#tao-so", "#so-du-doan"):
                assert frag not in href, (href, label)


def test_templates_have_no_prediction_wording():
    """Quét mọi template Jinja (bỏ chú thích {# #}); trang chủ và trang thống kê dùng chung các template này."""
    files = sorted((SITE / "templates").rglob("*.html"))
    assert files
    bad = []
    for f in files:
        text = re.sub(r"\{#.*?#\}", "", f.read_text(encoding="utf-8"), flags=re.S)
        bad += [f"{f.name}: {m.group(0)}" for m in FORBIDDEN.finditer(text)]
    assert not bad, bad


def test_site_routes_strings_have_no_prediction_wording():
    """Chuỗi trong routes.py (mô tả trang chủ, tiêu đề...), không tính docstring và chú thích."""
    tree = ast.parse((SITE / "routes.py").read_text(encoding="utf-8"))
    doc_ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            doc_ids.add(id(n.body[0].value))
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and id(n) not in doc_ids and FORBIDDEN.search(n.value)]
    assert not bad, bad


def test_telegram_message():
    d = {"game": "xs", "pname": "TP. Hồ Chí Minh", "draw_date": date(2026, 10, 26), "draw_seq": None}
    m = format_message("https://luckyvision.vn", "mn", d, {"db": ["472899"], "g1": ["78600"], "g8": ["74"]})
    assert "Đặc biệt: 472899" in m and "https://luckyvision.vn/xsmn-26-10-2026" in m
    g = {"game": "mega645", "pname": "Mega", "draw_date": date(2026, 11, 1), "draw_seq": 1583}
    m2 = format_message("https://luckyvision.vn/", "mega", g, {"main": ["05", "09", "17", "18", "34", "36"]})
    assert "kỳ 01583" in m2 and m2.endswith("/vietlott-mega-645-01-11-2026")


def _env():
    from luckyvision.site.routes import templates
    return templates.env


def test_num_chips_and_loto_chips_macros():
    env = _env()
    html = env.from_string(
        '{% from "macros.html" import num_chips, loto_chips %}'
        "{{ num_chips([(7, 12), ('27', 3)], 'ngày', 'hi') }}{{ loto_chips([5, 5, 27]) }}").render()
    assert 'class="rk-n has-cnt qs-c hi"' in html and "07</b><small" in html and "12 ngày" in html and "27</b><small" in html
    assert "05<sup>×2</sup>" in html and 'class="lt-n dup"' in html and "27</span>" in html


def test_stats_templates_use_chips_not_text_runs():
    env = _env()
    st = {"draws": 90, "recent": 30, "gan": [(1, 9)], "hot": [(27, 5), (3, 4)], "cold": [(8, 0)]}
    html = env.get_template("stats.html").render(h1="x", st=st, unit="ngày", summary="s")
    assert html.count("rk-n") >= 4 and "</b> (" not in html
    html = env.get_template("stats_pick.html").render(
        h1="x", draws=50, theory=0.1, recent=30, expected=3.0, rf={1: 2}, mx=2, gan=[(1, 4)],
        hot=[(5, 6)], cold=[(9, 0)], g=None)
    assert "rk-n has-cnt qs-c hi" in html and "</b> (" not in html
    html = env.get_template("stats_other.html").render(h1="x", draws=5, note="", bars_title="b", bars=[("1", 2)], bars_max=2,
                                                       hot=[("123", 2)])
    assert "rk-n has-cnt qs-c hi" in html and "</b> (" not in html


def test_home_quick_stats_use_chips():
    env = _env()
    snap = {"region_name": "miền Bắc", "as_of": "2026-11-05", "unit": "ngày",
            "gan_top": [{"number": "07", "days": 12}], "hot30": [{"number": "27", "count": 5}],
            "head_tail": {"dau": list(range(10)), "duoi": list(range(10))}}
    html = env.get_template("home.html").render(sections=[{"region": "mb", "title": "T", "url": "/xsmb", "when": "", "draws": [],
                                                           "display": [], "slug": "xsmb", "snap": snap}], games=[], short={})
    assert "rk-n has-cnt qs-c hi" in html and "12 ngày" in html and "5 lần" in html and 'class="qs-ht"' in html
    assert "</b> (" not in html


def test_game_result_uses_shared_chips():
    from luckyvision.domain.games import GAMES
    env = _env()
    t = env.from_string('{% from "macros_game.html" import game_result %}{{ game_result(g, d) }}')
    keno = t.render(g=GAMES["keno"], d={"prizes": {"main": ["05", "61"]}})
    assert 'class="rk-n"' in keno and 'class="rk-n hi"' in keno and "ball" not in keno
    dice = t.render(g=GAMES["bingo18"], d={"prizes": {"main": ["1", "2", "3"]}})
    assert "rk-n die" in dice and "= 6" in dice
    m3d = t.render(g=GAMES["max3d"], d={"prizes": {"db": ["123"], "g1": ["456"]}})
    assert "rk-groups" in m3d and ">ĐB<" in m3d and ">Nhất<" in m3d and "rk-n w3 sp" in m3d


def test_stats_scope_template_renders_options():
    """Thanh "Phạm vi thống kê" phải hiện đủ lựa chọn (khóa 'options', không trùng dict.items)."""
    from luckyvision.site.routes import templates
    t = templates.env.get_template("_stats_scope.html")
    html = t.render(scope={"kinds": [("/thong-ke-xsmn", "Miền Nam", True)], "label": "Đài",
                           "options": [("/thong-ke-xsmn", "Tất cả đài miền Nam", True), ("/thong-ke-xs-tp-hcm", "TP. Hồ Chí Minh", False)]})
    assert "Tất cả đài miền Nam" in html and "TP. Hồ Chí Minh" in html and "Loại xổ số" in html


def test_unknown_page_returns_html_not_found():
    """Đường dẫn sai: trang HTML "Không tìm thấy" (có menu), không phải JSON thô; API vẫn trả JSON."""
    import asyncio
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from luckyvision.api import errors
    from luckyvision.config import Settings
    app = FastAPI(); errors.install(app); app.state.settings = Settings()

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            return await c.get("/khong-ton-tai"), await c.get("/v1/khong-co")
    page, api = asyncio.run(go())
    assert page.status_code == 404 and "text/html" in page.headers["content-type"] and 'nav class="main"' in page.text
    assert api.status_code == 404 and api.json()["error"]["code"] == "not_found"
