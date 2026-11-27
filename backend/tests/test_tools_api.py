from datetime import datetime

import pytest

from xs247.api.errors import ApiError
from xs247.api.tools import encode, validate_doc
from xs247.config import VN_TZ

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=VN_TZ)


def test_encode_mb_and_reject_partial():
    pr = {"db": ["53401"], "g1": ["47745"], "g2": ["62988", "46737"], "g3": ["48305", "12492", "78217", "29106", "90525", "25381"],
          "g4": ["4352", "7734", "0900", "2827"], "g5": ["1885", "3123", "3284", "2452", "7149", "6951"], "g6": ["759", "626", "969"], "g7": ["96", "49", "18", "55"]}
    s = encode("mb", pr)
    assert s.startswith("5340147745") and len(s) == 107
    del pr["g7"]
    assert encode("mb", pr) is None


def test_locked_power_entries_cannot_change():
    old = {"entries": {"1417": [{"n": [1, 2, 3, 4, 5, 6], "t": 1}]}, "lo": {}}
    new = {"entries": {"1417": [{"n": [7, 8, 9, 10, 11, 12]}], "1419": [{"n": [1, 9, 29, 33, 38, 55]}]}, "lo": {}}
    out = validate_doc(old, new, 1418, NOW)
    assert out["entries"]["1417"] == old["entries"]["1417"]          # kỳ đã quay giữ nguyên
    assert out["entries"]["1419"][0]["n"] == [1, 9, 29, 33, 38, 55]   # kỳ chưa quay được thêm


def test_lo_lock_by_draw_time_and_validation():
    new = {"entries": {}, "lo": {"mn-tp-hcm-2026-11-03": [{"n": ["27", "8"]}], "mn-tp-hcm-2026-11-02": [{"n": ["01"]}]}}
    out = validate_doc({}, new, 0, NOW)
    assert out["lo"] == {"mn-tp-hcm-2026-11-03": [{"n": ["08", "27"], "t": out["lo"]["mn-tp-hcm-2026-11-03"][0]["t"]}]}
    late = datetime(2026, 11, 3, 16, 20, tzinfo=VN_TZ)
    assert validate_doc({}, new, 0, late)["lo"] == {}
    with pytest.raises(ApiError):
        validate_doc({}, {"entries": {"2000": [{"n": [1, 2, 3]}]}}, 1418, NOW)
