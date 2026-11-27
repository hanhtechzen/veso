"""Xác suất từng số: lý thuyết, tần suất lịch sử (kèm khoảng tin cậy), ước lượng mô hình, độ tin cậy mô hình.

Mục tiêu là giúp người dùng tự đánh giá: mọi con số đều được đặt cạnh mức lý thuyết và sai số ngẫu nhiên.
"""
from __future__ import annotations

import asyncio
import math
from datetime import date, datetime

from ..config import VN_TZ
from ..db import load_structure
from .models import counts_matrix, label, run_model, universe
from ..domain.games import GAMES, REGION_PROVINCE
from .service import load_history, truth_numbers


def theory_prob(game: str, numbers_per_draw: int) -> float:
    """Xác suất một số cụ thể xuất hiện trong một kỳ, khi kết quả hoàn toàn ngẫu nhiên.

    Lô tô: mỗi giải độc lập có 2 chữ số cuối đều từ 00–99, nên P = 1 - (99/100)^L.
    Power 6/55: 6 số khác nhau rút từ 55, nên P = 6/55.
    """
    if game in GAMES:
        return GAMES[game].main_count / GAMES[game].main_max
    return 1 - (1 - 1 / 100) ** numbers_per_draw


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy Wilson 95% cho tỉ lệ k/n."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def calibration_bins(pairs: list[tuple[float, int]], bins: int = 10) -> list[dict]:
    """Chia các cặp (xác suất dự báo, kết quả 0/1) thành các nhóm có số lượng bằng nhau."""
    if not pairs:
        return []
    pairs = sorted(pairs)
    total, k_bins = len(pairs), min(bins, len(pairs))
    out = []
    for i in range(k_bins):
        chunk = pairs[i * total // k_bins:(i + 1) * total // k_bins]
        n = len(chunk)
        k = sum(y for _, y in chunk)
        lo, hi = wilson(k, n)
        out.append({"predicted": sum(p for p, _ in chunk) / n, "observed": k / n, "ci_low": lo, "ci_high": hi, "count": n})
    return out


def default_province(region: str) -> str | None:
    return REGION_PROVINCE.get(region)


async def number_probabilities(conn, region: str, province: str, days: int) -> dict:
    today = datetime.now(VN_TZ).date()
    structure = await load_structure(conn, region, today)
    game = structure.game
    per_draw = structure.total_numbers if game == "xs" else GAMES[game].main_count
    theory = theory_prob(game, per_draw)
    size, lo = universe(game)

    all_days, all_draws, _ = await load_history(conn, province, date(9999, 1, 1))
    since = date.fromordinal(today.toordinal() - days) if days else date.min
    window = [(d, nums) for d, nums in zip(all_days, all_draws) if d >= since]
    n = len(window)
    appear = [0] * size
    for _, nums in window:
        for v in set(nums):
            if lo <= v < lo + size:
                appear[v - lo] += 1

    # Ước lượng mô hình cho kỳ tới: ưu tiên bản dự báo đã lưu, nếu chưa có thì tính trực tiếp
    model_probs: dict[str, dict[str, float]] = {}
    source = "computed"
    nxt = await (await conn.execute(
        """SELECT d.id FROM lottery_draws d WHERE d.province_code = %s AND d.current_version IS NULL
              AND d.scheduled_at > now() - interval '1 hour' ORDER BY d.scheduled_at LIMIT 1""", (province,))).fetchone()
    if nxt:
        rows = await (await conn.execute(
            "SELECT model, ranking, probs FROM forecasts WHERE draw_id = %s AND probs IS NOT NULL", (nxt["id"],))).fetchall()
        for r in rows:
            model_probs[r["model"]] = dict(zip(r["ranking"], r["probs"]))
        if rows:
            source = f"forecast:{nxt['id']}"
    if not model_probs and all_draws:
        C = counts_matrix(all_draws, game)
        for mid in ("dist", "logreg"):
            res = run_model(mid, C, region, "prob")
            if res and res[1] is not None:
                model_probs[mid] = {label(game, i): float(res[1][i]) for i in range(size)}

    items = []
    outside = 0
    for i in range(size):
        lab = label(game, i)
        k = appear[i]
        ci_lo, ci_hi = wilson(k, n)
        hist = k / n if n else None
        status = "no_data" if not n else ("high" if ci_lo > theory else "low" if ci_hi < theory else "normal")
        if status in ("high", "low"):
            outside += 1
        items.append({"number": lab, "theory": round(theory, 5), "historical": round(hist, 5) if hist is not None else None,
                      "ci_low": round(ci_lo, 5), "ci_high": round(ci_hi, 5), "appearances": k, "status": status,
                      "model": {m: round(p[lab], 5) for m, p in model_probs.items() if lab in p}})
    return {
        "region": region, "province": province, "game": game, "draws": n,
        "from": window[0][0].isoformat() if window else None, "to": window[-1][0].isoformat() if window else None,
        "theory": round(theory, 5), "numbers_per_draw": per_draw,
        "jackpot_odds": GAMES[game].jackpot_odds if game in GAMES else None,
        "outside_ci": outside, "expected_outside_by_chance": round(size * 0.05, 1),
        "model_source": source, "items": items,
    }


async def calibration(conn, region: str, province: str | None, model: str, days: int, bins: int = 10) -> dict:
    q = ["""SELECT f.ranking, f.probs, d.id, d.current_version, p.game
              FROM forecasts f JOIN lottery_draws d ON d.id = f.draw_id JOIN provinces p ON p.code = d.province_code
             WHERE f.model = %s AND f.probs IS NOT NULL AND d.current_version IS NOT NULL
               AND d.region_code = %s AND d.draw_date >= current_date - %s"""]
    args: list = [model, region, days]
    if province:
        q.append("AND d.province_code = %s"); args.append(province)
    rows = await (await conn.execute(" ".join(q), args)).fetchall()
    pairs: list[tuple[float, int]] = []
    for r in rows:
        res = await (await conn.execute(
            "SELECT prize_code, number FROM lottery_results WHERE draw_id = %s AND version = %s",
            (r["id"], r["current_version"]))).fetchall()
        prizes: dict[str, list[str]] = {}
        for x in res:
            prizes.setdefault(x["prize_code"], []).append(x["number"])
        truth = truth_numbers(r["game"], prizes)
        pairs += [(float(p), 1 if int(n) in truth else 0) for n, p in zip(r["ranking"], r["probs"])]
    b = calibration_bins(pairs, bins)
    total = len(pairs)
    return {"region": region, "province": province, "model": model, "days": days, "forecasts": len(rows),
            "points": total, "bins": b,
            "mean_predicted": round(sum(p for p, _ in pairs) / total, 5) if total else None,
            "mean_observed": round(sum(y for _, y in pairs) / total, 5) if total else None,
            "max_gap": round(max((abs(x["predicted"] - x["observed"]) for x in b), default=0), 5)}


_CAL_CACHE: dict[tuple, dict] = {}
_CAL_LOCK = asyncio.Semaphore(1)  # chống lạm dụng: tính toán nặng chạy lần lượt


def _backtest_pairs(draws: list[list[int]], game: str, region: str, model: str, last: int) -> list[tuple[float, int]]:
    C = counts_matrix(draws, game)
    size, lo = universe(game)
    pairs: list[tuple[float, int]] = []
    for t in range(max(1, len(draws) - last), len(draws)):
        res = run_model(model, C[:t], region, "cal")
        if not res or res[1] is None:
            continue
        probs = res[1]
        hit = C[t] > 0
        pairs += [(float(probs[i]), int(hit[i])) for i in range(size)]
    return pairs


async def calibration_backtest(conn, region: str, province: str, model: str, last: int = 120, bins: int = 10) -> dict:
    """Độ tin cậy tính bằng kiểm thử lùi: mỗi kỳ chỉ dùng các kỳ trước nó. Kết quả được lưu đệm theo dữ liệu mới nhất."""
    days, draws, game = await load_history(conn, province, date(9999, 1, 1))
    key = (province, model, last, days[-1] if days else None, len(days))
    if key not in _CAL_CACHE:
        async with _CAL_LOCK:
            if key in _CAL_CACHE:
                return {"region": region, "province": province, "model": model, "source": "backtest", "last": last,
                        **_CAL_CACHE[key]}
            pairs = await asyncio.to_thread(_backtest_pairs, draws, game, region, model, last)
            total = len(pairs)
            b = calibration_bins(pairs, bins)
            if len(_CAL_CACHE) > 50:
                _CAL_CACHE.clear()
            _CAL_CACHE[key] = {
                "points": total, "bins": b, "draws": total // universe(game)[0],
                "mean_predicted": round(sum(p for p, _ in pairs) / total, 5) if total else None,
                "mean_observed": round(sum(y for _, y in pairs) / total, 5) if total else None,
                "max_gap": round(max((abs(x["predicted"] - x["observed"]) for x in b), default=0), 5)}
    return {"region": region, "province": province, "model": model, "source": "backtest", "last": last, **_CAL_CACHE[key]}
