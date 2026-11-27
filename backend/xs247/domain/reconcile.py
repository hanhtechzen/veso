"""Đối chiếu kết quả giữa các nguồn (bước 6, mục 4 tài liệu thiết kế)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .prizes import Prizes


@dataclass(frozen=True)
class Candidate:
    id: int
    source_code: str
    priority: int
    checksum: str
    is_complete: bool
    payload: Prizes


@dataclass
class Decision:
    outcome: str  # 'verified' | 'conflict' | 'waiting'
    candidate_id: int | None = None
    sources: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)


def diff(a: Prizes, b: Prizes) -> list[dict]:
    out = []
    for code in sorted(set(a) | set(b)):
        xa, xb = a.get(code, []), b.get(code, [])
        for i in range(max(len(xa), len(xb))):
            va = xa[i] if i < len(xa) else None
            vb = xb[i] if i < len(xb) else None
            if va != vb:
                out.append({"prize": code, "position": i, "a": va, "b": vb})
    return out


def reconcile(candidates: list[Candidate], min_sources: int = 2) -> Decision:
    """Mỗi nguồn chỉ tính bản đầy đủ mới nhất của nó.

    - Đủ min_sources nguồn khác nhau cho cùng một kết quả: 'verified'.
    - Có từ hai nguồn đầy đủ nhưng kết quả khác nhau: 'conflict'.
    - Còn lại: 'waiting'.
    """
    latest: dict[str, Candidate] = {}
    for c in candidates:  # giả định danh sách đã sắp theo id tăng dần
        if c.is_complete and c.source_code != "manual":
            latest[c.source_code] = c
    groups: dict[str, list[Candidate]] = {}
    for c in latest.values():
        groups.setdefault(c.checksum, []).append(c)
    for members in sorted(groups.values(), key=len, reverse=True):
        if min_sources <= 1 and len(groups) > 1:
            break  # nhiều nguồn khác nhau: không tự chọn bản nào
        if len(members) >= min_sources:
            best = min(members, key=lambda c: (c.priority, c.id))
            return Decision("verified", best.id, sorted(m.source_code for m in members))
    if min_sources <= 1 and len(groups) == 1:
        members = next(iter(groups.values()))
        best = min(members, key=lambda c: (c.priority, c.id))
        return Decision("verified", best.id, sorted(m.source_code for m in members))
    if len(groups) > 1:
        reps = [min(m, key=lambda c: c.priority) for m in groups.values()]
        reps.sort(key=lambda c: c.priority)
        return Decision("conflict", None, sorted(latest), diff(reps[0].payload, reps[1].payload))
    return Decision("waiting", None, sorted(latest))
