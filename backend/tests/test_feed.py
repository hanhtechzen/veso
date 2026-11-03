from datetime import date

from luckyvision.domain.games import GAMES
from luckyvision.domain.prizes import DEFAULT_STRUCTURES, validate
from luckyvision.collector.feed import draw_id_for
from luckyvision.sources.vietlott_feed import parse_link_rows, parse_max3d_rows, parse_pick_rows

LOTTO = """<table><tr><th>Ngày</th></tr><tr><td>02/11/2026</td><td><a>00984</a></td><td>
<span class="bong_tron">04</span><span class="bong_tron">19</span><span class="bong_tron">25</span><span class="bong_tron">33</span>
<span class="bong_tron">35</span><span class="bong_tron no-margin-right">|</span><span class="bong_tron">05</span></td></tr></table>"""

KENO = """<table><tr><td><a href="#">03/11/2026</a><br><a href="#">#0301574</a></td><td><div>""" + "".join(
    f'<span class="bong_tron small">{n:02d}</span>' for n in [5, 7, 8, 13, 22, 28, 37, 39, 44, 46, 48, 49, 59, 60, 62, 63, 64, 66, 68, 70]) + \
    """</div></td><td>Chẵn (12)</td><td>Lớn (12)</td></tr></table>"""

BINGO = """<table><tr><td><a>03/11/2026</a> <a>#0194317</a></td><td><span>5</span><span>4</span><span>1</span></td><td>10</td><td>Hòa</td></tr></table>"""

DIGITS = "764109" + "789843033000" + "118947276069356706" + "111326994299937438811853"
MAX3D = ("""<table><tr><td><a href="#">01153</a><div>Ngày: 02/11/2026</div></td><td><div class="tong_day_so_ket_qua">"""
         + "".join(f'<span class="bong_tron small">{c}</span>' for c in DIGITS) + "</div></td></tr></table>")


def test_lotto535():
    r = parse_pick_rows(LOTTO, 5, True)
    assert len(r) == 1 and r[0].day == date(2026, 11, 2) and r[0].seq == 984
    assert r[0].prizes == {"main": ["04", "19", "25", "33", "35"], "special": ["05"]}
    assert validate(DEFAULT_STRUCTURES["lotto"], r[0].prizes) == []


def test_keno_and_bingo():
    k = parse_link_rows(KENO, 20, 2)[0]
    assert k.seq == 301574 and len(k.prizes["main"]) == 20 and validate(DEFAULT_STRUCTURES["keno"], k.prizes) == []
    b = parse_link_rows(BINGO, 3, 1)[0]
    assert b.seq == 194317 and b.prizes == {"main": ["5", "4", "1"]} and validate(DEFAULT_STRUCTURES["bingo"], b.prizes) == []


def test_max3d():
    r = parse_max3d_rows(MAX3D)[0]
    assert r.day == date(2026, 11, 2) and r.seq == 1153
    assert r.prizes["db"] == ["764", "109"] and r.prizes["g1"][3] == "000" and len(r.prizes["g3"]) == 8
    assert validate(DEFAULT_STRUCTURES["max3d"], r.prizes) == []


def test_draw_ids():
    assert draw_id_for(GAMES["keno"], date(2026, 11, 3), 301574) == "keno-keno-2026-11-03-0301574"
    assert draw_id_for(GAMES["lotto535"], date(2026, 11, 2), 984) == "lotto-lotto535-2026-11-02-00984"
    assert draw_id_for(GAMES["max3d"], date(2026, 11, 2), 1153) == "max3d-max3d-2026-11-02"


def test_odds():
    assert GAMES["lotto535"].jackpot_odds == 324632 * 12
    assert GAMES["power655"].jackpot_odds == 28989675 and GAMES["dt6x36"].jackpot_odds == 1947792
