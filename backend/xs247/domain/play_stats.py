"""Thống kê vé chơi thử của thành viên (thuần, không DB). Chỉ mô tả thói quen; không dự đoán.

Mỗi vé là dict: game, region, numbers, draw_date, cancelled_at, result (None = chưa dò; [] = không trúng;
danh sách {"code", "name"} = các giải trúng). Vé đã hủy bị loại hoàn toàn.
"""
from __future__ import annotations

import re
from collections import Counter
from math import comb


def _hyper_ge3(pool: int, pick: int = 6) -> float:
    """P(trùng >= 3 số) khi chọn 6 số trong `pool` số và kỳ quay lấy 6 số."""
    total = comb(pool, pick)
    return sum(comb(pick, k) * comb(pool - pick, pick - k) for k in range(3, pick + 1)) / total


# Xổ số truyền thống: (số lượng số trúng, số chữ số cuối phải khớp) của từng giải.
# Xấp xỉ: xác suất một vé trúng BẤT KỲ giải nào ~ tổng count / 10^digits (bỏ qua phần giao nhau giữa các giải,
# vốn rất nhỏ). Vé MB 5 số; vé MN/MT 6 số. Giải phụ đặc biệt và khuyến khích tính gần đúng bằng vài số hạng nhỏ.
_XS_MB = [(1, 5), (1, 5), (2, 5), (6, 5), (4, 4), (6, 4), (3, 3), (4, 2)]     # ĐB, G1..G7: 27 số
_XS_MB_EXTRA = [(1, 5)]                                                           # phụ ĐB/khuyến khích (gần đúng)
_XS_SOUTH = [(1, 2), (1, 3), (3, 4), (1, 4), (7, 5), (2, 5), (1, 5), (1, 5), (1, 6)]  # G8..ĐB: 18 số
_XS_SOUTH_EXTRA = [(1, 6), (1, 6)]                                                # phụ ĐB + khuyến khích (gần đúng)


def _p(spec) -> float:
    return sum(c / 10 ** d for c, d in spec)


WIN_PROBABILITY: dict[str, float] = {
    "xs_mb": _p(_XS_MB + _XS_MB_EXTRA),
    "xs_mn": _p(_XS_SOUTH + _XS_SOUTH_EXTRA),
    "xs_mt": _p(_XS_SOUTH + _XS_SOUTH_EXTRA),
    # Power 6/55: trúng giải khi trùng >= 3 số (jackpot 2 không đáng kể); Mega 6/45: trùng >= 3 số.
    "power655": _hyper_ge3(55),
    "mega645": _hyper_ge3(45),
    # Lotto 5/35: trúng khi >= 3 số chính hoặc trùng số đặc biệt (1/12); coi hai biến cố độc lập (xấp xỉ).
    "lotto535": 1 - (1 - sum(comb(5, k) * comb(30, 5 - k) for k in range(3, 6)) / comb(35, 5)) * (1 - 1 / 12),
    # Max 3D: một dãy 3 chữ số thuộc 20 số trúng ~ 20/1000. Max 3D Pro: xấp xỉ có ít nhất một số thuộc db/g1..g3
    # (2 + 18 số trên 1000, hai số của vé) ~ 2 * 20/1000. Chỉ để so sánh thô với số lần trúng thực tế.
    "max3d": 20 / 1000,
    "max3dpro": 2 * 20 / 1000,
}


def _live(tickets) -> list[dict]:
    return [t for t in tickets if not t.get("cancelled_at")]


def _key(t: dict) -> tuple:
    nums = [str(n) for n in t["numbers"]]
    if t["game"] in ("power655", "mega645"):
        nums = sorted(nums)
    elif t["game"] == "lotto535":
        nums = sorted(nums[:5]) + nums[5:]
    return (t["game"], t.get("region") or "", tuple(nums))


def _top(counter: Counter, n: int = 5) -> list[dict]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [{"number": k, "count": v} for k, v in items]


def summarize(tickets) -> dict:
    live = _live(tickets)
    total = len(live)
    checked = [t for t in live if t.get("result") is not None]
    won = [t for t in checked if t["result"]]
    by_game = Counter(t["game"] for t in live)
    tails: Counter = Counter()
    picks: Counter = Counter()
    vl_total = vl_small = 0
    seen: set = set()
    repeats = 0
    for t in live:
        k = _key(t)
        if k in seen:
            repeats += 1
        seen.add(k)
        if t["game"] == "xs":
            for n in t["numbers"]:
                tails[str(n)[-2:]] += 1
        elif t["game"] in ("max3d", "max3dpro"):
            for n in t["numbers"]:          # dãy 3 chữ số: đếm số hay chọn, không tính "ngày sinh"
                picks[str(n)] += 1
        else:
            for n in t["numbers"]:
                picks[str(n)] += 1
                vl_total += 1
                if int(n) <= 31:
                    vl_small += 1
    prizes: Counter = Counter()
    for t in won:
        for p in t["result"]:
            prizes[p["code"]] += 1
    expected = 0.0
    for t in checked:
        key = f"xs_{t.get('region')}" if t["game"] == "xs" else t["game"]
        expected += WIN_PROBABILITY.get(key, 0.0)
    return {
        "total": total, "checked": len(checked), "won": len(won), "pending": total - len(checked),
        "by_game": dict(by_game),
        "top_tail2": _top(tails), "top_pick": _top(picks),
        "repeat_rate": round(repeats / total, 2) if total else 0,
        "birthday_share": round(vl_small / vl_total, 2) if vl_total else None,
        "prizes": dict(prizes),
        "expected_wins": round(expected, 3) if checked else 0,
    }


SYSTEM_PROMPT = (
    "Bạn là trợ lý thân thiện của XS247, trả lời bằng tiếng Việt. Chỉ nhận xét thói quen chơi thử của người dùng "
    "dựa trên số liệu được cung cấp; không bịa thêm số liệu."
)


def ai_prompt(stats: dict) -> str:
    import json
    data = json.dumps(stats, ensure_ascii=False)
    return (
        "Dưới đây là thống kê vé chơi thử của một thành viên (các tỉ lệ ở dạng số thập phân, ví dụ 0.17 = 17%).\n"
        f"THỐNG KÊ: {data}\n\n"
        "Hãy nhận xét ngắn gọn, thân thiện (tối đa khoảng 150 từ) về THÓI QUEN chơi: mức độ lặp lại cùng bộ số "
        "(repeat_rate), xu hướng chọn số theo ngày sinh (birthday_share, các số <= 31), số lần trúng thực tế so với "
        "số lần trúng kỳ vọng (won so với expected_wins).\n"
        "Quy tắc bắt buộc: Không gợi ý số cụ thể, không nêu bất kỳ con số nào nên chọn, và không hứa hẹn tăng cơ hội trúng. "
        "Nhắc rằng mỗi kỳ quay là ngẫu nhiên và độc lập, và khuyên chơi trong khả năng, có chừng mực."
    )


_SENT = re.compile(r"[^.!?\n]+[.!?]*\s*|\n+")
_NUM = re.compile(r"\d{2,}")


def sanitize_comment(text: str) -> str:
    """Bỏ các câu có số từ 2 chữ số trở lên (nguy cơ là gợi ý số); giữ nguyên phần còn lại."""
    kept = [s for s in _SENT.findall(text or "") if not _NUM.search(s)]
    return "".join(kept).strip()
