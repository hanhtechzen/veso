"""Cơ cấu giải, kiểm tra và chuẩn hóa kết quả (mục 4 tài liệu thiết kế).

Mọi số được giữ dạng chuỗi để không mất số 0 ở đầu ("08", "010").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

Prizes = dict[str, list[str]]


@dataclass(frozen=True)
class PrizeSpec:
    code: str
    name: str
    count: int
    digits: int
    sort_order: int


@dataclass(frozen=True)
class Structure:
    region: str
    game: str  # 'xs' hoặc 'power655'
    prizes: tuple[PrizeSpec, ...] = field(default_factory=tuple)

    @property
    def codes(self) -> list[str]:
        return [p.code for p in self.prizes]

    def spec(self, code: str) -> PrizeSpec | None:
        return next((p for p in self.prizes if p.code == code), None)

    @property
    def total_numbers(self) -> int:
        return sum(p.count for p in self.prizes)


def _spec_list(rows: list[tuple[str, str, int, int]]) -> tuple[PrizeSpec, ...]:
    return tuple(PrizeSpec(c, n, cnt, dg, i) for i, (c, n, cnt, dg) in enumerate(rows, 1))


# Dùng cho kiểm thử và khi chưa đọc được bảng prize_structures.
DEFAULT_STRUCTURES: dict[str, Structure] = {
    "mb": Structure("mb", "xs", _spec_list([
        ("db", "Đặc biệt", 1, 5), ("g1", "Giải nhất", 1, 5), ("g2", "Giải nhì", 2, 5), ("g3", "Giải ba", 6, 5),
        ("g4", "Giải tư", 4, 4), ("g5", "Giải năm", 6, 4), ("g6", "Giải sáu", 3, 3), ("g7", "Giải bảy", 4, 2)])),
    "mn": Structure("mn", "xs", _spec_list([
        ("g8", "Giải tám", 1, 2), ("g7", "Giải bảy", 1, 3), ("g6", "Giải sáu", 3, 4), ("g5", "Giải năm", 1, 4),
        ("g4", "Giải tư", 7, 5), ("g3", "Giải ba", 2, 5), ("g2", "Giải nhì", 1, 5), ("g1", "Giải nhất", 1, 5),
        ("db", "Đặc biệt", 1, 6)])),
    "vl": Structure("vl", "power655", _spec_list([("main", "Bộ số chính", 6, 2), ("special", "Số đặc biệt", 1, 2)])),
}
DEFAULT_STRUCTURES["mt"] = Structure("mt", "xs", DEFAULT_STRUCTURES["mn"].prizes)


def normalize(raw: dict[str, list[object]], prize_map: dict[str, str] | None = None) -> Prizes:
    """Đổi mã giải về chuẩn (db, g1...) và số về chuỗi chỉ gồm chữ số."""
    prize_map = prize_map or {}
    out: Prizes = {}
    for key, values in raw.items():
        code = prize_map.get(key, key).strip().lower()
        nums = []
        for v in values or []:
            s = "".join(ch for ch in str(v) if not ch.isspace())
            if s:
                nums.append(s)
        out.setdefault(code, []).extend(nums)
    return out


def validate(structure: Structure, prizes: Prizes, *, partial: bool = False) -> list[str]:
    """Trả về danh sách lỗi; rỗng nghĩa là hợp lệ.

    partial=True: dùng trong lúc đang quay, cho phép thiếu giải nhưng số đã có phải đúng định dạng.
    """
    errors: list[str] = []
    known = set(structure.codes)
    for code in prizes:
        if code not in known:
            errors.append(f"Giải không có trong cơ cấu: {code}")
    for spec in structure.prizes:
        nums = prizes.get(spec.code, [])
        if len(nums) > spec.count:
            errors.append(f"{spec.name}: có {len(nums)} số, tối đa {spec.count}")
        if not partial and len(nums) != spec.count:
            errors.append(f"{spec.name}: cần {spec.count} số, hiện có {len(nums)}")
        for i, n in enumerate(nums, 1):
            if not n.isdigit():
                errors.append(f"{spec.name} số thứ {i} ({n}) không phải chữ số")
            elif len(n) != spec.digits:
                errors.append(f"{spec.name} số thứ {i} ({n}) cần {spec.digits} chữ số")
    if structure.game == "power655":
        errors.extend(_validate_power(prizes, partial=partial))
    return errors


def _validate_power(prizes: Prizes, *, partial: bool) -> list[str]:
    errors = []
    main = [n for n in prizes.get("main", []) if n.isdigit()]
    special = [n for n in prizes.get("special", []) if n.isdigit()]
    for n in main + special:
        if not 1 <= int(n) <= 55:
            errors.append(f"Số {n} nằm ngoài khoảng 01–55")
    if len(set(main)) != len(main):
        errors.append("Bộ số chính có số trùng nhau")
    if special and special[0] in main:
        errors.append("Số đặc biệt trùng với bộ số chính")
    return errors


def is_complete(structure: Structure, prizes: Prizes) -> bool:
    return all(len(prizes.get(p.code, [])) == p.count for p in structure.prizes)


def ordered(structure: Structure, prizes: Prizes) -> Prizes:
    """Sắp các giải theo thứ tự cơ cấu; Power 6/55 sắp bộ số chính tăng dần."""
    out: Prizes = {}
    for spec in sorted(structure.prizes, key=lambda p: p.sort_order):
        nums = list(prizes.get(spec.code, []))
        if structure.game == "power655" and spec.code == "main":
            nums.sort(key=int)
        if nums:
            out[spec.code] = nums
    return out


def checksum(prizes: Prizes) -> str:
    canon = json.dumps({k: prizes[k] for k in sorted(prizes)}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def loto(prizes: Prizes) -> list[str]:
    """Hai chữ số cuối của mọi giải (xổ số truyền thống)."""
    return [n[-2:] for nums in prizes.values() for n in nums]


def count_numbers(prizes: Prizes) -> int:
    return sum(len(v) for v in prizes.values())


def new_numbers(old: Prizes | None, new: Prizes) -> list[tuple[str, int, str]]:
    """Các số mới xuất hiện so với lần trước: (giải, vị trí bắt đầu từ 0, số)."""
    old = old or {}
    out = []
    for code, nums in new.items():
        prev = old.get(code, [])
        for i, n in enumerate(nums):
            if i >= len(prev) or prev[i] != n:
                out.append((code, i, n))
    return out
