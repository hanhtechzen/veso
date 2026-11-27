"""Tính năng AI dùng Claude API (tùy chọn, cần ANTHROPIC_API_KEY).

- Trợ lý trả lời câu hỏi về thống kê, chỉ dựa trên số liệu thật của hệ thống.
- AI chọn số theo mô tả của người dùng; kết quả luôn được kiểm tra lại bằng luật của trò chơi.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict, deque

import httpx

from .config import Settings
from .domain.games import GAMES, game_of_region

log = logging.getLogger(__name__)
BUSY_MSG = "Trợ lý AI đang bận, thử lại sau ít phút."


class AiError(Exception):
    pass


class RateLimiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, per_minute: int, window: float = 60) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= per_minute:
            return False
        q.append(now)
        return True


LIMITER = RateLimiter()


def build_request(settings: Settings, system: str, user: str, max_tokens: int) -> tuple[str, dict, dict]:
    """(địa chỉ, header, nội dung) theo nhà cung cấp đã chọn."""
    if settings.ai_provider == "openai":
        headers = {"content-type": "application/json"}
        if settings.ai_key:
            headers["authorization"] = f"Bearer {settings.ai_key}"
        return (settings.ai_url + "/chat/completions", headers,
                {"model": settings.ai_model_name, "max_tokens": max_tokens,
                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    return (settings.ai_url + "/v1/messages",
            {"x-api-key": settings.ai_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": settings.ai_model_name, "max_tokens": max_tokens, "system": system,
             "messages": [{"role": "user", "content": user}]})


def read_response(provider: str, data: dict) -> str:
    if provider == "openai":
        choices = data.get("choices") or [{}]
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content") or ""
        if isinstance(content, list):  # một số dịch vụ trả về danh sách đoạn
            content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        return content.strip()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


async def complete(settings: Settings, http: httpx.AsyncClient, system: str, user: str, max_tokens: int = 900) -> str:
    if not settings.ai_enabled:
        raise AiError("disabled")
    url, headers, body = build_request(settings, system, user, max_tokens)
    r = await http.post(url, timeout=60, headers=headers, json=body)
    if r.status_code != 200:
        # Nội dung lỗi của nhà cung cấp chỉ ghi nhật ký, không trả cho người dùng
        log.warning("Dịch vụ AI (%s) trả lỗi HTTP %s: %s", settings.ai_provider, r.status_code, r.text[:300])
        raise AiError(BUSY_MSG)
    return read_response(settings.ai_provider, r.json())


async def stats_context(conn, region: str, province: str | None) -> dict:
    """Số liệu thật đưa cho AI: kỳ gần đây, số về nhiều/ít, số gan, hiệu quả mô hình, dự báo kỳ tới."""
    prov_clause = "AND d.province_code = %s" if province else ""
    args = [region] + ([province] if province else [])
    rows = await (await conn.execute(f"""
        SELECT d.id, d.draw_date, d.province_code, p.game, r.prize_code, r.number
          FROM lottery_draws d JOIN provinces p ON p.code = d.province_code
          JOIN lottery_results r ON r.draw_id = d.id AND r.version = d.current_version
         WHERE d.region_code = %s {prov_clause} AND d.current_version IS NOT NULL
           AND d.draw_date >= (SELECT max(draw_date) FROM lottery_draws WHERE region_code = d.region_code) - 120
         ORDER BY d.draw_date""", args)).fetchall()
    draws: dict[str, dict] = {}
    for r in rows:
        d = draws.setdefault(r["id"], {"date": r["draw_date"].isoformat(), "province": r["province_code"],
                                       "game": r["game"], "prizes": {}})
        d["prizes"].setdefault(r["prize_code"], []).append(r["number"])
    items = list(draws.values())
    game = items[0]["game"] if items else game_of_region(region)

    def nums(d):
        if game in GAMES:
            return [int(n) for n in d["prizes"].get("main", [])]
        return [int(n[-2:]) for v in d["prizes"].values() for n in v]

    recent = items[-30:]
    counts: dict[int, int] = defaultdict(int)
    for d in recent:
        for n in nums(d):
            counts[n] += 1
    universe = range(1, GAMES[game].main_max + 1) if game in GAMES else range(100)
    order = sorted(universe, key=lambda n: (-counts[n], n))
    last_seen: dict[int, int] = {}
    for i, d in enumerate(items):
        for n in nums(d):
            last_seen[n] = i
    gaps = sorted(universe, key=lambda n: -(len(items) - 1 - last_seen.get(n, -1)))[:10]
    fmt = (lambda n: f"{n:02d}")
    perf = await (await conn.execute(
        """SELECT f.model, count(*) AS n,
                  avg((e.hits->>(CASE WHEN p.game IN ('power655', 'mega645') THEN '6' ELSE '10' END))::float) AS avg_hits,
                  avg((e.baseline->>(CASE WHEN p.game IN ('power655', 'mega645') THEN '6' ELSE '10' END))::float) AS avg_base
             FROM forecast_evaluations e JOIN forecasts f ON f.id = e.forecast_id
             JOIN lottery_draws d ON d.id = f.draw_id JOIN provinces p ON p.code = d.province_code
            WHERE d.region_code = %s GROUP BY f.model""", (region,))).fetchall()
    return {
        "game": (f"{GAMES[game].name} ({GAMES[game].main_count} số từ 01–{GAMES[game].main_max})" if game in GAMES
                 else "Xổ số truyền thống, lô tô 00–99"),
        "region": region, "province": province, "draws_analyzed": len(items),
        "latest_draws": [{"date": d["date"], "province": d["province"],
                          "numbers": " ".join(fmt(n) for n in nums(d))} for d in items[-5:]],
        "hot_last_30": [f"{fmt(n)} ({counts[n]} lần)" for n in order[:10]],
        "cold_last_30": [f"{fmt(n)} ({counts[n]} lần)" for n in order[-10:]],
        "longest_gaps": [f"{fmt(n)} ({len(items) - 1 - last_seen.get(n, -1)} kỳ)" for n in gaps],
        "model_performance": [{"model": p["model"], "forecasts": p["n"],
                               "avg_hits": round(p["avg_hits"] or 0, 3), "random_expected": round(p["avg_base"] or 0, 3)}
                              for p in perf],
    }


SYSTEM_ASK = """Bạn là trợ lý thống kê của XS247, trả lời bằng tiếng Việt, ngắn gọn, thân thiện.
Chỉ dùng số liệu trong phần DỮ LIỆU; không bịa thêm kết quả. Nếu dữ liệu không đủ để trả lời, nói rõ.
Luôn trung thực: mỗi kỳ quay là ngẫu nhiên và độc lập; số "nóng", số "gan" hay mô hình không làm tăng cơ hội trúng.
Không hứa hẹn trúng thưởng, không khuyến khích chơi nhiều hay chơi để gỡ. Nếu người dùng có dấu hiệu chơi quá mức,
nhẹ nhàng khuyên đặt giới hạn chi tiêu."""

SYSTEM_PICK = """Bạn giúp người dùng XS247 chọn số cho vui theo mô tả của họ (ngày sinh, số yêu thích, tránh số đẹp...).
Trả lời DUY NHẤT một JSON hợp lệ, không có chữ nào khác, dạng:
{"sets": [{"numbers": ["..", ".."], "reason": "giải thích ngắn bằng tiếng Việt"}], "note": "một câu nhắc đây là giải trí"}
Luật: {rule}. Không lặp số trong cùng một bộ. Không khẳng định bộ số nào dễ trúng hơn."""


def pick_rule(game: str, size: int) -> str:
    if game in GAMES:
        g = GAMES[game]
        return f"mỗi bộ gồm đúng {g.main_count} số khác nhau từ 01 đến {g.main_max}, viết 2 chữ số"
    return f"mỗi bộ gồm đúng {size} số lô khác nhau từ 00 đến 99, viết 2 chữ số"


def parse_pick(text: str, game: str, size: int, count: int) -> list[dict]:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise AiError("AI không trả về JSON")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise AiError(f"JSON không hợp lệ: {e}") from e
    lo, hi, need = (1, GAMES[game].main_max, GAMES[game].main_count) if game in GAMES else (0, 99, size)
    out = []
    for s in data.get("sets", [])[:count]:
        try:
            nums = sorted({int(str(x).strip()) for x in s.get("numbers", [])})
        except ValueError:
            continue
        if len(nums) == need and all(lo <= n <= hi for n in nums):
            out.append({"numbers": [f"{n:02d}" for n in nums], "reason": str(s.get("reason", ""))[:400]})
    if not out:
        raise AiError("AI không tạo được bộ số hợp lệ")
    return out
