"""Chơi thử: phần truy cập DB dùng chung cho API (api/play.py) và worker (dò vé định kỳ)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from psycopg.types.json import Jsonb

from .collector.planner import day_slots, make_draw_id
from .config import VN_TZ
from .domain.games import GAMES
from .domain.play import LOTTO_SLOTS, PICK_GAMES, check_ticket, closes_at

HORIZON_DAYS = 7
DAILY_LIMIT = 10
LOTTO = "lotto535"


def lotto_draw_id(day: date, slot: str) -> str:
    """Mã kỳ ảo của vé Lotto: 'lotto-lotto535-2026-11-12@1300' (kỳ thật mã theo số kỳ, nên vé chỉ nhớ ngày + giờ)."""
    return f"{make_draw_id(GAMES[LOTTO].region, LOTTO, day)}@{slot.replace(':', '')}"


def lotto_scheduled_at(day: date, slot: str) -> datetime:
    hh, mm = slot.split(":")
    return datetime.combine(day, time(int(hh), int(mm)), VN_TZ)


def resolve_lotto_draw(rows: list[dict], slot: str) -> dict | None:
    """Kỳ Lotto thật của một ngày ứng với khung giờ: kỳ đã công bố đầu tiên theo draw_seq = 13:00, kỳ thứ hai = 21:00."""
    ordered = sorted(rows, key=lambda r: r["draw_seq"])
    i = LOTTO_SLOTS.index(slot)
    return ordered[i] if i < len(ordered) else None


def _virtual_parts(draw_id: str) -> tuple[date, str] | None:
    if "@" not in (draw_id or ""):
        return None
    base, _, hhmm = draw_id.rpartition("@")
    try:
        return date.fromisoformat(base[-10:]), f"{hhmm[:2]}:{hhmm[2:]}"
    except ValueError:
        return None


async def resolve_lotto_rows(conn, rows: list[dict]) -> None:
    """Vé Lotto (mã kỳ ảo): gắn kỳ thật đã công bố của ngày đó vào hàng vé: real_draw_id, current_version, scheduled_at.
    Hàng đã có khóa real_draw_id thì bỏ qua. Kỳ chưa công bố -> real_draw_id None, current_version None."""
    todo = [r for r in rows if "real_draw_id" not in r and _virtual_parts(r.get("draw_id"))]
    if not todo:
        return
    days = sorted({_virtual_parts(r["draw_id"])[0] for r in todo})
    pub = await (await conn.execute(
        """SELECT id, draw_date, draw_seq, current_version, status, scheduled_at FROM lottery_draws
            WHERE game = 'lotto535' AND draw_date = ANY(%s) AND current_version IS NOT NULL
            ORDER BY draw_date, draw_seq""", (days,))).fetchall()
    by_day: dict[date, list[dict]] = {}
    for d in pub:
        by_day.setdefault(d["draw_date"], []).append(d)
    for r in todo:
        day, slot = _virtual_parts(r["draw_id"])
        r["scheduled_at"] = lotto_scheduled_at(day, slot)
        d = resolve_lotto_draw(by_day.get(day, []), slot) if slot in LOTTO_SLOTS else None
        r["real_draw_id"] = d["id"] if d else None
        r["current_version"] = d["current_version"] if d else None


def prize_key(r: dict) -> str:
    """Mã kỳ dùng để tra giải: kỳ thật cho vé Lotto, còn lại là draw_id của vé."""
    return r.get("real_draw_id") or r["draw_id"]


async def open_draws(conn, now: datetime) -> list[dict]:
    """Kỳ quay còn nhận vé trong 7 ngày tới (theo lịch + ngày nghỉ), bỏ kỳ đã có kết quả hiện hành."""
    today = now.astimezone(VN_TZ).date()
    days = [today + timedelta(days=i) for i in range(HORIZON_DAYS)]
    done = {r["id"] for r in await (await conn.execute(
        "SELECT id, current_version FROM lottery_draws WHERE draw_date BETWEEN %s AND %s AND current_version IS NOT NULL",
        (days[0], days[-1]))).fetchall() if r.get("current_version") is not None}
    out = []
    for day in days:
        for slot in LOTTO_SLOTS:       # Lotto 5/35: 2 kỳ mỗi ngày, kỳ ảo theo (ngày, giờ)
            sched = lotto_scheduled_at(day, slot)
            close = closes_at(sched, LOTTO)
            if now >= close:
                continue
            out.append({"id": lotto_draw_id(day, slot), "game": LOTTO, "region": GAMES[LOTTO].region, "province": LOTTO,
                        "province_name": GAMES[LOTTO].name, "draw_date": day.isoformat(), "slot": slot,
                        "scheduled_at": sched.isoformat(), "closes_at": close.isoformat()})
        for s in await day_slots(conn, day):
            game = s["game"]
            if game == "xs":
                if s["region_code"] not in ("mb", "mn", "mt"):
                    continue
                province = s["province_code"]
            elif game in PICK_GAMES or game in ("max3d", "max3dpro"):
                province = game
            else:
                continue
            did = make_draw_id(s["region_code"], s["province_code"], day)
            sched = datetime.combine(day, s["draw_time"], VN_TZ)
            close = closes_at(sched, game)
            if did in done or now >= close:
                continue
            out.append({"id": did, "game": game, "region": s["region_code"], "province": province,
                        "province_name": s["province_name"], "draw_date": day.isoformat(),
                        "scheduled_at": sched.isoformat(), "closes_at": close.isoformat()})
    out.sort(key=lambda x: (x["scheduled_at"], x["id"]))
    return out


def draw_id_for(game: str, region: str, province: str | None, day: date) -> str:
    """Mã kỳ quay của vé: xổ số theo (miền, đài); Vietlott theo (miền của trò chơi, mã trò chơi)."""
    if game == "xs":
        return make_draw_id(region, province or "", day)
    return make_draw_id(GAMES[game].region, game, day)


async def published_prizes(conn, draw_ids: list[str]) -> dict[str, dict[str, list[str]]]:
    """Giải của phiên bản hiện hành theo kỳ quay: {draw_id: {prize_code: [số, ...]}} (chỉ đọc)."""
    res = await (await conn.execute(
        """SELECT r.draw_id, r.prize_code, r.position, r.number FROM lottery_results r
             JOIN lottery_draws d ON d.id = r.draw_id AND r.version = d.current_version
            WHERE r.draw_id = ANY(%s) ORDER BY r.draw_id, r.prize_code, r.position""",
        (list(draw_ids),))).fetchall()
    prizes: dict[str, dict[str, list[str]]] = {}
    for x in res:
        prizes.setdefault(x["draw_id"], {}).setdefault(x["prize_code"], []).append(x["number"])
    return prizes


async def check_rows(conn, rows: list[dict]) -> int:
    """Dò các vé (hàng có id, game, region_code, numbers, draw_id, current_version, checked_version) mà kỳ quay đã
    có kết quả và chưa dò theo phiên bản hiện hành. Ghi result + checked_version, sửa tại chỗ các hàng.
    Trả về số vé đã ghi."""
    await resolve_lotto_rows(conn, rows)
    todo = [r for r in rows if r.get("current_version") is not None and r.get("checked_version") != r["current_version"]]
    if not todo:
        return 0
    prizes = await published_prizes(conn, sorted({prize_key(r) for r in todo}))
    n = 0
    for r in todo:
        pr = prizes.get(prize_key(r))
        if not pr:
            continue
        result = check_ticket(r["game"], r.get("region_code") or "", list(r["numbers"]), pr)
        await conn.execute("UPDATE play_tickets SET result = %s, checked_version = %s WHERE id = %s",
                           (Jsonb(result), r["current_version"], r["id"]))
        r["result"], r["checked_version"] = result, r["current_version"]
        n += 1
    return n


async def check_pending(conn, batch: int = 500) -> int:
    """Việc nền của worker: dò các vé chưa dò (hoặc kết quả đã đổi phiên bản) của kỳ đã quay, theo lô."""
    total = 0
    while True:
        rows = await (await conn.execute(
            """SELECT t.id, t.game, t.region_code, t.numbers, t.draw_id, d.current_version, t.checked_version
                 FROM play_tickets t JOIN lottery_draws d ON d.id = t.draw_id
                WHERE t.cancelled_at IS NULL AND d.current_version IS NOT NULL
                  AND (t.checked_version IS NULL OR t.checked_version <> d.current_version)
                ORDER BY t.id LIMIT %s""", (batch,))).fetchall()
        done = await check_rows(conn, rows)
        total += done
        if len(rows) < batch or done == 0:
            break
    # vé Lotto: mã kỳ ảo nên không nối được theo t.draw_id; dò theo kỳ thật của ngày (chưa dò, hoặc 7 ngày gần đây
    # để bắt kết quả đổi phiên bản). Duyệt theo id để vé của kỳ chưa công bố không chặn các vé sau.
    last = 0
    while True:
        rows = await (await conn.execute(
            """SELECT t.id, t.game, t.region_code, t.numbers, t.draw_id, t.draw_date, t.checked_version
                 FROM play_tickets t
                WHERE t.game = 'lotto535' AND t.cancelled_at IS NULL AND t.id > %s
                  AND (t.checked_version IS NULL OR t.draw_date >= %s)
                ORDER BY t.id LIMIT %s""", (last, datetime.now(VN_TZ).date() - timedelta(days=7), batch))).fetchall()
        if not rows:
            return total
        rows = [dict(r) for r in rows]
        total += await check_rows(conn, rows)
        last = rows[-1]["id"]
        if len(rows) < batch:
            return total
