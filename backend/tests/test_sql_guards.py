"""Kiểm tra tĩnh: không còn câu lệnh dựa vào ràng buộc 'mỗi đài một kỳ mỗi ngày' đã bỏ ở migration 009."""
from pathlib import Path


def test_no_conflict_target_on_removed_constraint():
    root = Path(__file__).resolve().parents[1] / "luckyvision"
    bad = [str(p) for p in root.rglob("*.py") if "ON CONFLICT (province_code, draw_date)" in p.read_text(encoding="utf-8")]
    assert not bad, bad
