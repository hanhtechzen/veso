"""Kiểm thử bộ đọc của các bộ cào với HTML mẫu mô phỏng cấu trúc trang thật."""
from datetime import date

from luckyvision.config import Settings
from luckyvision.domain.prizes import DEFAULT_STRUCTURES, validate
from luckyvision.domain.reconcile import Candidate, reconcile
from luckyvision.sources.base import DrawRef, FetchResult
from luckyvision.sources.html_util import by_class, strip_tags
from luckyvision.sources.minhngoc import MinhNgocAdapter, parse_text
from luckyvision.sources.vietlott import VietlottPower655Adapter, parse_rows
from luckyvision.sources.xosocomvn import XosoComVnAdapter, parse_html, parse_multi, province_code

MINHNGOC = """<html><body><div class="box_kqxs">
<a href="/ket-qua-xo-so/mien-nam/tp-hcm/19-10-2026.html">Xem kỳ trước 19/10/2026</a>
<h3>XSHCM ngày 26/10/2026</h3><table>
<tr><td>Giải tám</td><td><div>74</div></td></tr><tr><td>Giải bảy</td><td><div>010</div></td></tr>
<tr><td>Giải s&aacute;u</td><td><div>3452</div><div>9687</div><div>3427</div></td></tr>
<tr><td>Giải năm</td><td><div>3987</div></td></tr>
<tr><td>Giải tư</td><td><div>78899</div><div>13421</div><div>69122</div><div>62142</div><div>48887</div><div>90540</div><div>68727</div></td></tr>
<tr><td>Giải ba</td><td><div>79446</div><div>35158</div></td></tr><tr><td>Giải nh&igrave;</td><td><div>54677</div></td></tr>
<tr><td>Giải nhất</td><td><div>78600</div></td></tr><tr><td>Giải ĐB</td><td><div>472899</div></td></tr></table>
<h3>XSHCM ngày 25/10/2026</h3><table><tr><td>Giải tám</td><td>11</td></tr></table></div></body></html>"""


def test_minhngoc_parse_full_and_validates():
    p = parse_text(strip_tags(MINHNGOC), date(2026, 10, 26), "mn")
    assert p["db"] == ["472899"] and p["g7"] == ["010"] and len(p["g4"]) == 7
    assert validate(DEFAULT_STRUCTURES["mn"], p) == []


def test_minhngoc_other_date_and_partial():
    assert parse_text(strip_tags(MINHNGOC), date(2026, 10, 25), "mn") == {}
    assert parse_text(strip_tags(MINHNGOC), date(2026, 10, 25), "mn", allow_partial=True) == {"g8": ["11"]}


def test_minhngoc_url():
    ad = MinhNgocAdapter("m", {}, Settings())
    ref = DrawRef("mn-vung-tau-2026-10-27", "xs", "mn", "vung-tau", date(2026, 10, 27))
    assert ad._url(ref) == "https://www.minhngoc.net/ket-qua-xo-so/mien-nam/vung-tau/27-10-2026.html"


XOSO = """<table class="table-result"><tr><th>ĐB</th><td><span class="special-prize">53401</span></td></tr>
<tr><td><span class="prize1">47745</span></td></tr><tr><td><span class="prize2">62988</span><span class="prize2">46737</span></td></tr>
<tr><td>""" + "".join(f'<span class="prize3">{n}</span>' for n in ["48305", "12492", "78217", "29106", "90525", "25381"]) + """</td></tr>
<tr><td>""" + "".join(f'<span class="prize4">{n}</span>' for n in ["4352", "7734", "0900", "2827"]) + """</td></tr>
<tr><td>""" + "".join(f'<span class="prize5">{n}</span>' for n in ["1885", "3123", "3284", "2452", "7149", "6951"]) + """</td></tr>
<tr><td><span class="prize6">759</span><span class="prize6">626</span><span class="prize6">969</span></td></tr>
<tr><td><span class="prize7"><b>96</b></span><span class="prize7">49</span><span class="prize7">18</span><span class="prize7">55</span></td></tr></table>"""


def test_xosocomvn_parse_keeps_leading_zero():
    p = parse_html(XOSO)
    assert p["g4"][2] == "0900" and p["g7"] == ["96", "49", "18", "55"]
    assert validate(DEFAULT_STRUCTURES["mb"], p) == []
    ad = XosoComVnAdapter("x", {}, Settings())
    assert ad._url(DrawRef("mb-mb-2026-10-29", "xs", "mb", "mb", date(2026, 10, 29))) == "https://xoso.com.vn/xsmb-29-10-2026.html"


def test_by_class_nested_and_void_tags():
    out = by_class('<div class="a">1<br>2<span class="b">3</span></div><p class="a">4</p>', {"a", "b"})
    assert out == {"a": ["123", "4"], "b": ["3"]}


VIETLOTT = """<table class="table"><thead><tr><th>Ngày</th><th>Kỳ</th><th>Kết quả</th></tr></thead><tbody>
<tr><td>29/10/2026</td><td><a href="#">01417</a></td><td><div class="day_so_ket_qua_v2">
<span class="bong_tron small">09</span><span class="bong_tron small">29</span><span class="bong_tron small">33</span>
<span class="bong_tron small">38</span><span class="bong_tron small">45</span><span class="bong_tron small">46</span>
<span class="bong_tron small no-margin-right">|</span><span class="bong_tron small">53</span></div></td></tr>
<tr><td>27/10/2026</td><td>01416</td><td><span>9</span><span>18</span><span>27</span><span>28</span><span>31</span><span>35</span><span>|</span><span>50</span></td></tr>
</tbody></table>"""


def test_vietlott_rows_and_parse():
    rows = parse_rows(VIETLOTT)
    assert rows[0] == {"date": date(2026, 10, 29), "seq": 1417, "main": ["09", "29", "33", "38", "45", "46"], "special": "53"}
    assert rows[1]["main"][0] == "09"  # tự thêm số 0
    ad = VietlottPower655Adapter("v", {}, Settings())
    ref = DrawRef("vl-power655-2026-10-27", "power655", "vl", "power655", date(2026, 10, 27))
    p = ad.parse(FetchResult("u", 200, VIETLOTT.encode()), ref)
    assert p.prizes == {"main": ["09", "18", "27", "28", "31", "35"], "special": ["50"]}
    assert p.meta == {"draw_seq": 1416}
    assert validate(DEFAULT_STRUCTURES["vl"], p.prizes) == []


def test_single_source_threshold():
    a = {"db": ["1"]}
    c = Candidate(1, "vietlott-web", 10, "x", True, a)
    assert reconcile([c], min_sources=1).outcome == "verified"
    assert reconcile([c], min_sources=2).outcome == "waiting"
    s = Settings(min_sources_by_region="vl:1, mb:2", min_matching_sources=3)
    assert (s.min_sources("vl"), s.min_sources("mb"), s.min_sources("mn")) == (1, 2, 3)


XSMT = """<table class="table-result table-xsmn"><thead><tr><th>Giải</th><th><a href="/xsdng">Đà Nẵng</a></th>
<th><a href="/xskh">Khánh Hòa</a></th></tr></thead><tbody>
<tr><th>G8</th><td><span>16</span></td><td>72</td></tr>
<tr><th>G7</th><td>055</td><td>931</td></tr>
<tr><th>G6</th><td>0571<br>2219<br>2252</td><td>1111<br>2222<br>3333</td></tr>
<tr><th>G5</th><td>5709</td><td>4444</td></tr>
<tr><th>G4</th><td>80925 32129 56660 06232 37027 32270 73261</td><td>11111 22222 33333 44444 55555 66666 77777</td></tr>
<tr><th>G3</th><td>98428 35348</td><td>12121 34343</td></tr>
<tr><th>G2</th><td>53993</td><td>...</td></tr>
<tr><th>G1</th><td>47765</td><td>...</td></tr>
<tr><th>ĐB</th><td>065878</td><td>...</td></tr></tbody></table>
<table class="table-result"><tr><th>khác</th></tr></table>"""


def test_xosocomvn_multi_province_and_partial():
    t = parse_multi(XSMT)
    assert set(t) == {"danang", "khanhhoa"}
    dn = t["danang"]
    assert dn["db"] == ["065878"] and dn["g4"][3] == "06232" and dn["g7"] == ["055"]
    assert validate(DEFAULT_STRUCTURES["mt"], dn) == []
    kh = t["khanhhoa"]
    assert "db" not in kh and validate(DEFAULT_STRUCTURES["mt"], kh, partial=True) == []
    ad = XosoComVnAdapter("x", {}, Settings())
    ref = DrawRef("mt-da-nang-2026-10-28", "xs", "mt", "da-nang", date(2026, 10, 28))
    assert ad._url(ref) == "https://xoso.com.vn/xsmt-28-10-2026.html"
    assert ad.parse(FetchResult("u", 200, XSMT.encode()), ref).prizes["g1"] == ["47765"]


def test_province_name_matching():
    assert province_code("Thừa Thiên Huế") == "thuathienhue" == province_code("Huế")
    assert province_code("TP. HCM") == "tphcm" and province_code("Đắk Lắk") == "daklak"
    assert province_code("Đà Lạt") == "dalat" == province_code("Lâm Đồng")
    assert province_code("Bà Rịa - Vũng Tàu") == "vungtau"
