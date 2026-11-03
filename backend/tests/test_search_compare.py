from datetime import date

from luckyvision.site.compare import analyze, parse_numbers
from luckyvision.site.search import norm, parse

PROVS = [{"code": "tp-hcm", "name": "TP. Hồ Chí Minh", "region_code": "mn"}, {"code": "da-nang", "name": "Đà Nẵng", "region_code": "mt"},
         {"code": "dong-nai", "name": "Đồng Nai", "region_code": "mn"}, {"code": "dak-nong", "name": "Đắk Nông", "region_code": "mt"}]
T = date(2026, 11, 3)


def test_norm():
    assert norm("Xổ Số ĐÀ NẴNG") == "xo so da nang"


def test_parse_cases():
    i = parse("xsmn 26/10", PROVS, T); assert i.region == "mn" and i.day == date(2026, 10, 26)
    i = parse("lô 27 tp hcm", PROVS, T); assert i.province == "tp-hcm" and i.lo == ["27"]
    i = parse("power kỳ 1417", PROVS, T); assert i.game == "power655" and i.seq == 1417
    i = parse("Xổ số Đà Nẵng thứ 7", PROVS, T); assert i.province == "da-nang" and i.day == date(2026, 10, 31) and not i.lo
    i = parse("vé 472899", PROVS, T); assert i.tickets == ["472899"]
    i = parse("xsmb 25/12", PROVS, T); assert i.day == date(2025, 12, 25)  # ngày tương lai -> năm trước
    i = parse("power 6/55 29/10", PROVS, T); assert i.game == "power655" and i.day == date(2026, 10, 29)
    i = parse("đắk nông", PROVS, T); assert i.province == "dak-nong"
    i = parse("lịch quay", PROVS, T); assert i.topic == "lich-quay"


def test_compare():
    draws = [{"draw_date": date(2026, 10, d), "pname": "X", "loto": l, "prizes": {}} for d, l in
             [(1, [27, 5]), (2, [72]), (3, [27, 72, 27]), (4, [1]), (5, [27])]]
    r = analyze(draws, [27, 72], pick=False, universe=range(0, 100), p_theory=0.2)
    a, b = r["per"]
    assert a["hits"] == 3 and a["occ"] == 4 and a["gap_now"] == 0 and a["max_gap"] == 2 and a["avg_gap"] == 2.0
    assert b["hits"] == 2 and b["gap_now"] == 2 and r["pairs"][0]["both"] == 1
    assert a["partners"][0]["n"] in (5, 72) and a["timeline"] == [True, False, True, False, True]
    assert parse_numbers("27, 72, 272, 7", 0, 99) == [27, 72, 7]
