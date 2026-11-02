import asyncio
from datetime import date

import pytest

from luckyvision.collector.context import SourceGate
from luckyvision.collector.planner import make_draw_id, parse_draw_id
from luckyvision.config import Settings
from luckyvision.sources.base import DrawRef, FetchResult, ParseError
from luckyvision.sources.fixture import FixtureAdapter
from luckyvision.sources.http_json import HttpJsonAdapter
from pathlib import Path

FX = str(Path(__file__).resolve().parents[1] / "fixtures")


def test_draw_id_roundtrip():
    i = make_draw_id("mn", "tp-hcm", date(2026, 10, 26))
    assert i == "mn-tp-hcm-2026-10-26"
    assert parse_draw_id(i) == ("mn", "tp-hcm", date(2026, 10, 26))
    assert parse_draw_id("vl-power655-2026-10-29")[1] == "power655"


async def test_fixture_adapter_reads_and_404():
    ad = FixtureAdapter("fixture-a", {}, Settings(fixture_dir=FX))
    ref = DrawRef("mb-mb-2026-10-29", "xs", "mb", "mb", date(2026, 10, 29))
    res = await ad.fetch(None, ref)
    assert res.status == 200
    assert ad.parse(res, ref).prizes["db"] == ["53401"]
    miss = await ad.fetch(None, DrawRef("mb-mb-2000-01-01", "xs", "mb", "mb", date(2000, 1, 1)))
    assert miss.status == 404


def test_http_json_parse_with_mapping():
    ad = HttpJsonAdapter("p", {"url_template": "https://x/{province}/{date}", "prizes_path": "data.prizes",
                               "complete_path": "data.complete"}, Settings())
    body = b'{"data": {"complete": true, "prizes": {"DB": ["472899"], "G8": "74"}}}'
    p = ad.parse(FetchResult("u", 200, body), None)
    assert p.prizes == {"DB": ["472899"], "G8": ["74"]} and p.complete is True
    with pytest.raises(ParseError):
        ad.parse(FetchResult("u", 200, b'{"other": 1}'), None)
    ref = DrawRef("mn-tp-hcm-2026-10-26", "xs", "mn", "tp-hcm", date(2026, 10, 26))
    assert ad._url(ref) == "https://x/tp-hcm/2026-10-26"


async def test_gate_rate_limit_and_breaker():
    g = SourceGate(max_failures=2, cooldown_s=60)
    t0 = asyncio.get_running_loop().time()
    await g.wait_turn("s", 100)
    await g.wait_turn("s", 100)
    assert asyncio.get_running_loop().time() - t0 >= 0.09
    assert not g.failure("s")
    assert g.failure("s") and g.is_open("s")


def test_admin_tokens_parse():
    s = Settings(admin_tokens="short:admin:x, 0123456789abcdef0123456789:admin:An,abcdefghijklmnopqrstuvwx:editor,"
                              "thay-bang-token-ngau-nhien-dai:admin:mau")
    m = s.admin_token_map()
    assert "short" not in m and "thay-bang-token-ngau-nhien-dai" not in m
    assert m["0123456789abcdef0123456789"] == ("admin", "An")
    assert m["abcdefghijklmnopqrstuvwx"] == ("editor", "editor")
