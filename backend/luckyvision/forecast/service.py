"""Tạo dự báo trước giờ quay, đánh giá sau khi có kết quả, tổng hợp hiệu quả mô hình."""
from __future__ import annotations

import logging
import math
from datetime import date

import numpy as np
from psycopg.types.json import Jsonb

from .models import MODELS, counts_matrix, label, normalize, rank, run_model, universe

log = logging.getLogger(__name__)
K_VALUES = {"xs": (5, 10, 20), "power655": (6,)}
MIN_EVAL = 20  # dưới số kỳ này chưa kết luận tốt hay kém hơn ngẫu nhiên


async def load_history(conn, province: str, before: date, limit: int = 1500) -> tuple[list[date], list[list[int]], str]:
    """Các kỳ đã công bố của một đài trước ngày 'before': (ngày, danh sách số, loại trò chơi)."""
    p = await (await conn.execute("SELECT game FROM provinces WHERE code = %s", (province,))).fetchone()
    game = p["game"] if p else "xs"
    rows = await (await conn.execute(
        """WITH ds AS (SELECT id, draw_date, current_version FROM lottery_draws
                        WHERE province_code = %s AND draw_date < %s AND current_version IS NOT NULL
                        ORDER BY draw_date DESC LIMIT %s)
           SELECT ds.draw_date, r.prize_code, r.number
             FROM ds JOIN lottery_results r ON r.draw_id = ds.id AND r.version = ds.current_version
            ORDER BY ds.draw_date""", (province, before, limit))).fetchall()
    by_day: dict[date, list[int]] = {}
    for r in rows:
        if game == "power655":
            if r["prize_code"] == "main":
                by_day.setdefault(r["draw_date"], []).append(int(r["number"]))
        else:
            by_day.setdefault(r["draw_date"], []).append(int(r["number"][-2:]))
    days = sorted(by_day)[-limit:]
    return days, [by_day[d] for d in days], game


def truth_numbers(game: str, prizes: dict[str, list[str]]) -> set[int]:
    if game == "power655":
        return {int(n) for n in prizes.get("main", [])}
    return {int(n[-2:]) for nums in prizes.values() for n in nums}


async def generate_for_draw(conn, draw: dict) -> int:
    """Tạo dự báo cho một kỳ chưa quay. Không ghi đè dự báo đã có. Trả về số dự báo mới."""
    existing = {r["model"] for r in await (await conn.execute(
        "SELECT model FROM forecasts WHERE draw_id = %s", (draw["id"],))).fetchall()}
    todo = [m for m in MODELS if m.id not in existing]
    if not todo:
        return 0
    days, draws, game = await load_history(conn, draw["province_code"], draw["draw_date"])
    if not draws:
        return 0
    C = counts_matrix(draws, game)
    made = 0
    for m in todo:
        out = run_model(m.id, C, draw["region_code"], draw["id"])
        if out is None:
            continue
        scores, probs, params = out
        order = rank(scores)
        await conn.execute(
            """INSERT INTO forecasts (id, draw_id, model, version, window_from, window_to, window_n,
                                      ranking, scores, probs, params)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (draw_id, model) DO NOTHING""",
            (f"{draw['id']}:{m.id}", draw["id"], m.id, m.version, days[0], days[-1], len(days),
             Jsonb([label(game, i) for i in order]), Jsonb(normalize(scores, order)),
             Jsonb([round(float(probs[i]), 6) for i in order]) if probs is not None else None, Jsonb(params)))
        made += 1
    return made


async def generate_upcoming(pool) -> int:
    """Dự báo cho mọi kỳ chưa quay trong hôm nay và ngày mai."""
    async with pool.connection() as conn:
        draws = await (await conn.execute(
            """SELECT * FROM lottery_draws
                WHERE current_version IS NULL AND scheduled_at > now()
                  AND draw_date <= (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date + 1
                ORDER BY scheduled_at""")).fetchall()
    total = 0
    for d in draws:
        async with pool.connection() as conn:
            total += await generate_for_draw(conn, d)
    if total:
        log.info("Đã tạo %d dự báo mới", total)
    return total


def score_forecast(game: str, ranking: list[str], probs: list[float] | None, params: dict,
                   truth: set[int]) -> dict:
    size, lo = universe(game)
    ks = K_VALUES[game]
    nums = [int(x) for x in ranking]
    hits = {str(k): sum(1 for n in nums[:k] if n in truth) for k in ks}
    base = {str(k): round(k * len(truth) / size, 4) for k in ks}
    brier = brier_u = None
    if probs:
        y = np.array([1.0 if n in truth else 0.0 for n in nums])
        pr = np.array(probs)
        if game == "power655":
            pr = np.clip(pr, 0, 1)
        brier = float(np.mean((pr - y) ** 2))
        q = float(params.get("q", len(truth) / size))
        brier_u = float(np.mean((q - y) ** 2))
    return {"truth_size": len(truth), "hits": hits, "baseline": base, "brier": brier, "brier_uniform": brier_u}


async def evaluate_pending(pool) -> int:
    async with pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT f.*, d.current_version, p.game FROM forecasts f
                 JOIN lottery_draws d ON d.id = f.draw_id
                 JOIN provinces p ON p.code = d.province_code
                 LEFT JOIN forecast_evaluations e ON e.forecast_id = f.id
                WHERE d.current_version IS NOT NULL AND (e.forecast_id IS NULL OR e.draw_version <> d.current_version)
                LIMIT 2000""")).fetchall()
        done = 0
        cache: dict[str, set[int]] = {}
        for f in rows:
            key = f"{f['draw_id']}@{f['current_version']}"
            if key not in cache:
                res = await (await conn.execute(
                    "SELECT prize_code, number FROM lottery_results WHERE draw_id = %s AND version = %s",
                    (f["draw_id"], f["current_version"]))).fetchall()
                prizes: dict[str, list[str]] = {}
                for r in res:
                    prizes.setdefault(r["prize_code"], []).append(r["number"])
                cache[key] = truth_numbers(f["game"], prizes)
            s = score_forecast(f["game"], f["ranking"], f["probs"], f["params"], cache[key])
            await conn.execute(
                """INSERT INTO forecast_evaluations (forecast_id, draw_version, truth_size, hits, baseline, brier, brier_uniform)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (forecast_id) DO UPDATE SET draw_version = EXCLUDED.draw_version, evaluated_at = now(),
                     truth_size = EXCLUDED.truth_size, hits = EXCLUDED.hits, baseline = EXCLUDED.baseline,
                     brier = EXCLUDED.brier, brier_uniform = EXCLUDED.brier_uniform""",
                (f["id"], f["current_version"], s["truth_size"], Jsonb(s["hits"]), Jsonb(s["baseline"]),
                 s["brier"], s["brier_uniform"]))
            done += 1
    if done:
        log.info("Đã chấm %d dự báo", done)
    return done


def summarize(rows: list[dict], k: int) -> dict:
    """Tổng hợp Precision@K so với ngẫu nhiên, kèm khoảng tin cậy 95%."""
    key = str(k)
    rows = [r for r in rows if key in r["hits"]]
    n = len(rows)
    if not n:
        return {"n": 0}
    prec = [r["hits"][key] / k for r in rows]
    base = [r["baseline"][key] / k for r in rows]
    diff = [a - b for a, b in zip(prec, base)]
    mean = sum(diff) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in diff) / max(1, n - 1))
    ci = 1.96 * sd / math.sqrt(n)
    briers = [r for r in rows if r["brier"] is not None]
    return {
        "n": n, "k": k,
        "hit_count": sum(r["hits"][key] for r in rows),
        "precision": round(sum(prec) / n, 4),
        "baseline_precision": round(sum(base) / n, 4),
        "diff": round(mean, 4), "ci95": round(ci, 4),
        "verdict": ("insufficient" if n < MIN_EVAL else
                    "better" if mean - ci > 0 else "worse" if mean + ci < 0 else "no_difference"),
        "hit_rate": round(sum(1 for r in rows if r["hits"][key] > 0) / n, 4),
        "brier": round(sum(r["brier"] for r in briers) / len(briers), 5) if briers else None,
        "brier_uniform": round(sum(r["brier_uniform"] for r in briers) / len(briers), 5) if briers else None,
    }


def backtest(draws: list[list[int]], game: str, region: str, last: int, k: int, models: list[str] | None = None,
             province: str = "x") -> dict[str, dict]:
    """Kiểm thử lùi trong bộ nhớ: mỗi kỳ chỉ dùng các kỳ trước nó."""
    C = counts_matrix(draws, game)
    T = len(draws)
    out: dict[str, list[dict]] = {m.id: [] for m in MODELS if not models or m.id in models}
    for t in range(max(1, T - last), T):
        truth = set(np.nonzero(C[t])[0] + universe(game)[1])
        for mid in out:
            res = run_model(mid, C[:t], region, f"{province}-{t}")
            if res is None:
                continue
            scores, probs, params = res
            order = rank(scores)
            s = score_forecast(game, [label(game, i) for i in order],
                               [float(probs[i]) for i in order] if probs is not None else None, params,
                               {int(x) for x in truth})
            out[mid].append(s)
    return {mid: summarize(rows, k) for mid, rows in out.items()}
