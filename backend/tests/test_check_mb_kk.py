"""Miền Bắc: giải Khuyến khích (trùng 2 số cuối giải ĐB) và tên giải ĐB phụ thuộc ký hiệu; Lotto KK khi chỉ trùng số ĐB."""
from luckyvision.domain.play import check_ticket

MB = {"db": ["12345"], "g1": ["67890"], "g7": ["45", "99", "05", "11"]}


def codes(r):
    return [x["code"] for x in r]


def test_mb_kk_two_last_digits_of_db():
    assert "kk" in codes(check_ticket("xs", "mb", ["00045"], MB))
    assert codes(check_ticket("xs", "mb", ["00077"], MB)) == []


def test_mb_full_db_not_also_kk_and_name_mentions_kyhieu():
    r = check_ticket("xs", "mb", ["12345"], MB)
    assert "db" in codes(r) and "kk" not in codes(r)
    assert "ký hiệu" in next(x["name"] for x in r if x["code"] == "db")


def test_mn_unaffected():
    MN = {"db": ["123456"], "g8": ["12"]}
    assert "kk" not in codes(check_ticket("xs", "mn", ["000056"], MN))


def test_lotto_kk_with_only_special():
    pr = {"main": ["01", "02", "03", "04", "05"], "special": ["07"]}
    assert codes(check_ticket("lotto535", "lotto", ["10", "11", "12", "13", "14", "07"], pr)) == ["kk"]
    assert codes(check_ticket("lotto535", "lotto", ["10", "11", "12", "13", "14", "08"], pr)) == []
