"""Gửi kết quả mới công bố lên kênh Telegram công khai (TELEGRAM_RESULTS_CHAT_ID)."""
from __future__ import annotations

import logging

from .domain.games import GAMES
from .site.data import REGION_NAMES, REGION_SLUG, compact, dmy, slug_date, weekday

log = logging.getLogger(__name__)


def format_message(site_url: str, region: str, draw: dict, prizes: dict[str, list[str]]) -> str:
    site = site_url.rstrip("/")
    if draw["game"] in GAMES:
        g = GAMES[draw["game"]]
        if g.code in ("keno", "bingo18"):
            return ""  # quay vài phút một kỳ: không gửi từng kỳ để tránh làm phiền
        ky = f" kỳ {draw['draw_seq']:0{g.seq_width}d}," if draw["draw_seq"] else ","
        return (f"{g.name}{ky} {weekday(draw['draw_date'])} {dmy(draw['draw_date'])}\n"
                f"{compact(g, {'prizes': prizes})}\n{site}/{g.slug}-{slug_date(draw['draw_date'])}")
    db = prizes.get("db", ["?"])[0]
    g1 = prizes.get("g1", ["?"])[0]
    loto = " ".join(sorted({n[-2:] for v in prizes.values() for n in v}))
    head = "Xổ số miền Bắc" if region == "mb" else f"Xổ số {draw['pname']} ({REGION_NAMES[region]})"
    return (f"{head}, {weekday(draw['draw_date'])} {dmy(draw['draw_date'])}\nĐặc biệt: {db}\nGiải nhất: {g1}\nLô tô: {loto}\n"
            f"{site}/{REGION_SLUG[region]}-{slug_date(draw['draw_date'])}")


async def on_events(pool, http, settings, rows: list[dict]) -> None:
    """Được gọi sau khi chuyển sự kiện sang Redis; chỉ xử lý sự kiện công bố lần đầu."""
    if not (settings.telegram_bot_token and settings.telegram_results_chat_id):
        return
    ids = [r["payload"].get("draw_id") for r in rows if r["topic"] == "draw.published" and (r["payload"] or {}).get("version") == 1]
    ids = [i for i in ids if i]
    if not ids:
        return
    async with pool.connection() as conn:
        for draw_id in ids:
            d = await (await conn.execute(
                """SELECT d.*, p.name AS pname FROM lottery_draws d JOIN provinces p ON p.code = d.province_code WHERE d.id = %s""",
                (draw_id,))).fetchone()
            if not d or not d["current_version"]:
                continue
            res = await (await conn.execute(
                "SELECT prize_code, number FROM lottery_results WHERE draw_id = %s AND version = %s ORDER BY prize_code, position",
                (draw_id, d["current_version"]))).fetchall()
            prizes: dict[str, list[str]] = {}
            for r in res:
                prizes.setdefault(r["prize_code"], []).append(r["number"])
            text = format_message(settings.site_url, d["region_code"], d, prizes)
            if not text:
                continue
            try:
                await http.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                                json={"chat_id": settings.telegram_results_chat_id, "text": text, "disable_web_page_preview": True},
                                timeout=10)
            except Exception:  # noqa: BLE001
                log.exception("Không gửi được kết quả %s lên Telegram", draw_id)
