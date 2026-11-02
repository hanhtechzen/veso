import json
from pathlib import Path

from luckyvision.domain.prizes import (DEFAULT_STRUCTURES, checksum, is_complete, loto, new_numbers, normalize,
                                       ordered, validate)

FX = Path(__file__).resolve().parents[1] / "fixtures"


def load(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))["prizes"]


def test_fixtures_are_valid():
    for name, region in (("mb-mb-2026-10-29", "mb"), ("mn-tp-hcm-2026-10-26", "mn"), ("vl-power655-2026-10-29", "vl")):
        s = DEFAULT_STRUCTURES[region]
        p = load(name)
        assert validate(s, p) == [], name
        assert is_complete(s, p)


def test_mb_has_27_numbers_and_loto():
    p = load("mb-mb-2026-10-29")
    assert DEFAULT_STRUCTURES["mb"].total_numbers == 27
    lo = loto(p)
    assert len(lo) == 27 and lo[0] == "01" and "00" in lo  # 0900 -> 00, giữ số 0


def test_wrong_digits_and_missing_prize():
    s = DEFAULT_STRUCTURES["mn"]
    p = load("mn-tp-hcm-2026-10-26")
    p["g7"] = ["10"]  # mất số 0 ở đầu
    del p["g1"]
    errs = validate(s, p)
    assert any("Giải bảy" in e and "3 chữ số" in e for e in errs)
    assert any("Giải nhất" in e and "cần 1 số" in e for e in errs)


def test_partial_allows_missing_but_not_bad_format():
    s = DEFAULT_STRUCTURES["mn"]
    assert validate(s, {"g8": ["74"], "g7": ["010"]}, partial=True) == []
    assert validate(s, {"g8": ["7"]}, partial=True)
    assert not is_complete(s, {"g8": ["74"]})


def test_unknown_prize_rejected():
    assert validate(DEFAULT_STRUCTURES["mb"], {"g9": ["12"]}, partial=True)


def test_power_rules():
    s = DEFAULT_STRUCTURES["vl"]
    assert validate(s, {"main": ["09", "29", "33", "38", "45", "56"], "special": ["53"]})       # 56 > 55
    assert validate(s, {"main": ["09", "09", "33", "38", "45", "46"], "special": ["53"]})       # trùng
    assert validate(s, {"main": ["09", "29", "33", "38", "45", "46"], "special": ["46"]})       # đặc biệt trùng
    assert ordered(s, {"special": ["53"], "main": ["46", "09", "33", "29", "45", "38"]})["main"][0] == "09"


def test_normalize_maps_and_strips():
    out = normalize({"DB": [" 472 899 "], "G8": [74]}, {"DB": "db", "G8": "g8"})
    assert out == {"db": ["472899"], "g8": ["74"]}


def test_checksum_ignores_key_order():
    a = {"db": ["1"], "g1": ["2"]}
    b = {"g1": ["2"], "db": ["1"]}
    assert checksum(a) == checksum(b)
    assert checksum(a) != checksum({"db": ["1"], "g1": ["3"]})


def test_new_numbers():
    assert new_numbers(None, {"g8": ["74"]}) == [("g8", 0, "74")]
    assert new_numbers({"g6": ["3452"]}, {"g6": ["3452", "9687"]}) == [("g6", 1, "9687")]
