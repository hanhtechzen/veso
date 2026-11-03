from datetime import date

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


def test_telegram_message():
    d = {"game": "xs", "pname": "TP. Hồ Chí Minh", "draw_date": date(2026, 10, 26), "draw_seq": None}
    m = format_message("https://luckyvision.vn", "mn", d, {"db": ["472899"], "g1": ["78600"], "g8": ["74"]})
    assert "Đặc biệt: 472899" in m and "https://luckyvision.vn/xsmn-26-10-2026" in m
    g = {"game": "mega645", "pname": "Mega", "draw_date": date(2026, 11, 1), "draw_seq": 1583}
    m2 = format_message("https://luckyvision.vn/", "mega", g, {"main": ["05", "09", "17", "18", "34", "36"]})
    assert "kỳ 01583" in m2 and m2.endswith("/vietlott-mega-645-01-11-2026")
