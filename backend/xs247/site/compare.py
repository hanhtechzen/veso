"""So sánh các con số: tần suất, số kỳ chưa về, khoảng cách giữa các lần về, số hay về cùng."""
from __future__ import annotations

from itertools import combinations


def _sets(draws: list[dict], pick: bool) -> list[tuple[set[int], list[int]]]:
    out = []
    for d in draws:
        nums = [int(x) for x in d["prizes"].get("main", [])] if pick else list(d["loto"])
        out.append((set(nums), nums))
    return out


def analyze(draws: list[dict], numbers: list[int], *, pick: bool, universe: range, p_theory: float, timeline: int = 40) -> dict:
    """draws: cũ trước, mới sau. p_theory: xác suất một số có mặt trong một kỳ khi kết quả hoàn toàn ngẫu nhiên."""
    sets = _sets(draws, pick)
    n = len(draws)
    per = []
    for x in numbers:
        idx = [i for i, (s, _) in enumerate(sets) if x in s]
        occ = sum(lst.count(x) for _, lst in sets)
        gaps = [b - a for a, b in zip(idx, idx[1:])]
        max_gap = max([idx[0]] + gaps + [n - 1 - idx[-1]]) if idx else n
        last = draws[idx[-1]] if idx else None
        # Số hay về cùng: trong các kỳ có x, số nào xuất hiện nhiều nhất
        co: dict[int, int] = {}
        for i in idx:
            for y in sets[i][0]:
                if y != x:
                    co[y] = co.get(y, 0) + 1
        partners = sorted(co.items(), key=lambda t: (-t[1], t[0]))[:5]
        per.append({
            "n": x, "hits": len(idx), "occ": occ, "pct": len(idx) / n if n else 0, "expected": p_theory * n,
            "gap_now": (n - 1 - idx[-1]) if idx else n, "max_gap": max_gap,
            "avg_gap": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "last_date": last["draw_date"] if last else None, "last_place": last.get("pname") if last else None,
            "partners": [{"n": y, "co": c, "rate": c / len(idx) if idx else 0} for y, c in partners],
            "timeline": [x in s for s, _ in sets[-timeline:]],
        })
    pairs = []
    for a, b in combinations(numbers, 2):
        both = sum(1 for s, _ in sets if a in s and b in s)
        pairs.append({"a": a, "b": b, "both": both, "expected": round(p_theory * p_theory * n, 1)})
    return {"draws": n, "per": per, "pairs": pairs, "p_theory": p_theory,
            "timeline_dates": [d["draw_date"] for d in draws[-timeline:]], "universe": [universe.start, universe.stop - 1]}


def parse_numbers(text: str, lo: int, hi: int, limit: int = 4) -> list[int]:
    import re
    out: list[int] = []
    for t in re.findall(r"\d+", text or ""):
        v = int(t)
        if lo <= v <= hi and v not in out and len(t) <= 2:
            out.append(v)
    return out[:limit]
