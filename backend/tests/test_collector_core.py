"""Lõi bộ thu thập: cổng ngắt mạch (SourceGate), Settings.min_sources, parse_draw_id.
Các test này mô tả hành vi hiện tại (đúng), nhằm khóa lại khi sửa mã.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from xs247.collector import context
from xs247.collector.context import SourceGate
from xs247.collector.planner import parse_draw_id
from xs247.config import Settings


# ---------- SourceGate ----------
@pytest.fixture
def clock(monkeypatch):
    t = [1000.0]
    # Thay riêng tên `time` trong context để không đụng tới đồng hồ của vòng lặp asyncio
    monkeypatch.setattr(context, "time", SimpleNamespace(monotonic=lambda: t[0]))
    return t


def test_gate_opens_after_max_failures(clock):
    g = SourceGate(max_failures=3, cooldown_s=600)
    assert g.failure("a") is False and g.failure("a") is False
    assert not g.is_open("a")
    assert g.failure("a") is True
    assert g.is_open("a")
    assert not g.is_open("other")  # theo từng nguồn


def test_gate_reopens_after_cooldown(clock):
    g = SourceGate(max_failures=2, cooldown_s=600)
    g.failure("a")
    assert g.failure("a") is True
    clock[0] += 599
    assert g.is_open("a")
    clock[0] += 2
    assert not g.is_open("a")


def test_gate_success_resets_failure_count(clock):
    g = SourceGate(max_failures=2, cooldown_s=600)
    g.failure("a")
    g.success("a")
    assert g.failure("a") is False
    assert not g.is_open("a")


def test_gate_failure_counter_restarts_after_tripping(clock):
    g = SourceGate(max_failures=2, cooldown_s=10)
    g.failure("a"); g.failure("a")
    clock[0] += 11
    assert g.failure("a") is False  # đếm lại từ đầu
    assert g.failure("a") is True


# ---------- Settings.min_sources ----------
def S(**kw):
    return Settings(_env_file=None, min_matching_sources=2, **kw)


def test_min_sources_parses_region_list_with_spaces():
    s = S(min_sources_by_region="mb:2, mn:3,vl:1")
    assert s.min_sources("mb") == 2
    assert s.min_sources("mn") == 3
    assert s.min_sources("vl") == 1


def test_min_sources_zero_is_raised_to_one():
    assert S(min_sources_by_region="mn:0").min_sources("mn") == 1


@pytest.mark.parametrize("raw", ["", "garbage", "mn:", "mn:x", "mn:-1", ",,,", "mn=3"])
def test_min_sources_garbage_falls_back_to_default(raw):
    assert S(min_sources_by_region=raw).min_sources("mn") == 2


def test_min_sources_unlisted_region_uses_default():
    assert S(min_sources_by_region="mb:3").min_sources("mn") == 2


# ---------- parse_draw_id ----------
def test_parse_draw_id_basic():
    assert parse_draw_id("mn-tp-hcm-2026-10-26") == ("mn", "tp-hcm", date(2026, 10, 26))
    assert parse_draw_id("mb-mb-2026-10-29") == ("mb", "mb", date(2026, 10, 29))
    assert parse_draw_id("vl-power655-2026-10-29") == ("vl", "power655", date(2026, 10, 29))


def test_parse_draw_id_with_trailing_draw_number_keno():
    assert parse_draw_id("vl-keno-2026-11-03-0301574") == ("vl", "keno", date(2026, 11, 3))


@pytest.mark.parametrize("bad", ["mn-tp-hcm-2026-13-40", "mb-mb-2026-02-30", "", "mb-mb", "nonsense", "mb-2026-10-29x", None])
def test_parse_draw_id_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_draw_id(bad)
