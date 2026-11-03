"""Dữ liệu cho trang Công cụ (/cong-cu/) và sổ dự đoán của thành viên.

GET  /v1/export/tools          toàn bộ kết quả Power 6/55 và 3 năm gần nhất của ba miền, dạng gọn
PUT  /v1/user/predictions      lưu sổ dự đoán (chỉ được thêm cho kỳ chưa quay; kỳ đã quay bị khóa)
GET  /v1/predictions/board     bảng xếp hạng chung (tên hiển thị + dự đoán)
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response

from ..config import VN_TZ
from .errors import ApiError
from .user import need_user

router = APIRouter(tags=["tools"])
# Thứ tự giải khi ghép thành chuỗi số, khớp với trang Công cụ (MB_ENC, MN_ENC)
ENC = {"mb": [("db", 1, 5), ("g1", 1, 5), ("g2", 2, 5), ("g3", 6, 5), ("g4", 4, 4), ("g5", 6, 4), ("g6", 3, 3), ("g7", 4, 2)],
       "mn": [("db", 1, 6), ("g1", 1, 5), ("g2", 1, 5), ("g3", 2, 5), ("g4", 7, 5), ("g5", 1, 4), ("g6", 3, 4), ("g7", 1, 3), ("g8", 1, 2)]}
ENC["mt"] = ENC["mn"]
DRAW_TIME = {"mb": (18, 15), "mn": (16, 15), "mt": (17, 15)}
_CACHE: dict = {}


def encode(region: str, prizes: dict[str, list[str]]) -> str | None:
    out = []
    for code, count, width in ENC[region]:
        nums = prizes.get(code, [])
        if len(nums) != count or any(len(n) != width or not n.isdigit() for n in nums):
            return None
        out += nums
    return "".join(out)


async def build_export(conn, years: int) -> dict:
    power = []
    rows = await (await conn.execute(
        """SELECT d.draw_seq, d.draw_date, r.prize_code, r.number FROM lottery_draws d
             JOIN lottery_results r ON r.draw_id = d.id AND r.version = d.current_version
            WHERE d.province_code = 'power655' AND d.current_version IS NOT NULL AND d.draw_seq IS NOT NULL
            ORDER BY d.draw_seq, r.prize_code, r.position""")).fetchall()
    cur: dict = {}
    for r in rows:
        d = cur.setdefault(r["draw_seq"], {"date": r["draw_date"], "main": [], "special": []})
        d[r["prize_code"]].append(int(r["number"]))
    for seq, d in sorted(cur.items()):
        if len(d["main"]) == 6:
            power.append([seq, *sorted(d["main"]), d["special"][0] if d["special"] else 0, d["date"].isoformat()])
    since = datetime.now(VN_TZ).date() - timedelta(days=365 * years)
    rg: dict = {"mb": [], "mn": {}, "mt": {}}
    rows = await (await conn.execute(
        """SELECT d.id, d.region_code, d.province_code, d.draw_date, r.prize_code, r.number FROM lottery_draws d
             JOIN lottery_results r ON r.draw_id = d.id AND r.version = d.current_version
            WHERE d.region_code IN ('mb', 'mn', 'mt') AND d.current_version IS NOT NULL AND d.draw_date >= %s
            ORDER BY d.draw_date, d.id, r.prize_code, r.position""", (since,))).fetchall()
    draws: dict = {}
    for r in rows:
        x = draws.setdefault(r["id"], {"region": r["region_code"], "prov": r["province_code"], "date": r["draw_date"], "pr": {}})
        x["pr"].setdefault(r["prize_code"], []).append(r["number"])
    for x in draws.values():
        digits = encode(x["region"], x["pr"])
        if not digits:
            continue
        item = [x["date"].isoformat(), digits]
        if x["region"] == "mb":
            rg["mb"].append(item)
        else:
            rg[x["region"]].setdefault(x["prov"], []).append(item)
    return {"generated_at": datetime.now(VN_TZ).isoformat(timespec="seconds"), "power": power, "rg": rg}


@router.get("/v1/export/tools")
async def export_tools(request: Request, response: Response, years: int = Query(3, ge=1, le=20)):
    async with request.app.state.pool.connection() as conn:
        mark = await (await conn.execute(
            """SELECT count(*) AS n, max(published_at) AS p FROM lottery_draws
                WHERE current_version IS NOT NULL AND region_code IN ('mb', 'mn', 'mt', 'vl')""")).fetchone()
        key = f"{years}|{mark['n']}|{mark['p']}"
        etag = '"' + hashlib.sha1(key.encode()).hexdigest()[:16] + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=60"})
        if _CACHE.get("key") != key:
            data = await build_export(conn, years)
            _CACHE.update(key=key, body=json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    return Response(_CACHE["body"], media_type="application/json",
                    headers={"ETag": etag, "Cache-Control": "public, max-age=60"})


# ---------------- Sổ dự đoán ----------------
LO_KEY = re.compile(r"^(mb|mn|mt)-([a-z0-9-]+)-(\d{4}-\d{2}-\d{2})$")


async def _locked_power(conn) -> int:
    r = await (await conn.execute("""SELECT max(draw_seq) AS s FROM lottery_draws WHERE province_code = 'power655'
                                      AND current_version IS NOT NULL""")).fetchone()
    return r["s"] or 0


def _lo_open(key: str, now: datetime) -> bool:
    m = LO_KEY.match(key)
    if not m:
        return False
    day = datetime.strptime(m[3], "%Y-%m-%d").date()
    h, mi = DRAW_TIME[m[1]]
    return now < datetime(day.year, day.month, day.day, h, mi, tzinfo=VN_TZ)


def validate_doc(old: dict, new: dict, latest_power: int, now: datetime) -> dict:
    """Chỉ cho thêm hoặc sửa dự đoán của kỳ chưa quay; dự đoán của kỳ đã quay giữ nguyên như cũ."""
    out = {"entries": {}, "lo": {}}
    old_e, old_l = old.get("entries") or {}, old.get("lo") or {}
    new_e, new_l = new.get("entries") or {}, new.get("lo") or {}
    if not isinstance(new_e, dict) or not isinstance(new_l, dict) or len(new_e) > 2000 or len(new_l) > 2000:
        raise ApiError(422, "invalid_doc", "Dữ liệu sổ dự đoán không hợp lệ")
    ts = int(time.time() * 1000)
    for k, v in old_e.items():  # kỳ đã quay: khóa
        if k.isdigit() and int(k) <= latest_power:
            out["entries"][k] = v
    for k, v in new_e.items():
        if not k.isdigit() or int(k) <= latest_power:
            continue
        if not isinstance(v, list) or len(v) > 3:
            raise ApiError(422, "invalid_doc", "Mỗi kỳ tối đa 3 bộ số")
        items = []
        for e in v:
            n = sorted({int(x) for x in (e.get("n") or []) if str(x).isdigit()})
            if len(n) != 6 or not all(1 <= x <= 55 for x in n):
                raise ApiError(422, "invalid_doc", "Bộ số Power gồm 6 số khác nhau từ 01 đến 55")
            old_t = next((o.get("t") for o in old_e.get(k, []) if sorted(o.get("n", [])) == n), None)
            items.append({"n": n, "t": old_t or ts})
        out["entries"][k] = items
    for k, v in old_l.items():
        if not _lo_open(k, now):
            out["lo"][k] = v
    for k, v in new_l.items():
        if not LO_KEY.match(k) or not _lo_open(k, now):
            continue
        if not isinstance(v, list) or len(v) > 3:
            raise ApiError(422, "invalid_doc", "Mỗi kỳ tối đa 3 lần khóa")
        items = []
        for e in v:
            n = sorted({str(x).zfill(2)[-2:] for x in (e.get("n") or []) if str(x).isdigit()})
            if not 1 <= len(n) <= 5:
                raise ApiError(422, "invalid_doc", "Mỗi lần khóa tối đa 5 số lô")
            old_t = next((o.get("t") for o in old_l.get(k, []) if sorted(o.get("n", [])) == n), None)
            items.append({"n": n, "t": old_t or ts})
        out["lo"][k] = items
    return out


@router.put("/v1/user/predictions")
async def save_predictions(request: Request, u: dict = Depends(need_user)):
    try:
        new = json.loads((await request.body())[:500_000] or b"{}")
    except ValueError:
        raise ApiError(422, "invalid_doc", "Dữ liệu không hợp lệ")
    async with request.app.state.pool.connection() as conn:
        row = await (await conn.execute("SELECT doc FROM user_prediction_docs WHERE user_id = %s FOR UPDATE", (u["id"],))).fetchone()
        doc = validate_doc(row["doc"] if row else {}, new, await _locked_power(conn), datetime.now(VN_TZ))
        await conn.execute("""INSERT INTO user_prediction_docs (user_id, doc, updated_at) VALUES (%s, %s, now())
                              ON CONFLICT (user_id) DO UPDATE SET doc = EXCLUDED.doc, updated_at = now()""",
                           (u["id"], json.dumps(doc)))
    return {"doc": doc}


@router.get("/v1/predictions/board")
async def board(request: Request, response: Response):
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT u.id, u.display_name, p.doc FROM user_prediction_docs p JOIN users u ON u.id = p.user_id
                WHERE NOT u.disabled ORDER BY p.updated_at DESC LIMIT 1000""")).fetchall()
    response.headers["Cache-Control"] = "private, no-cache"
    return {"items": [{"id": f"u{r['id']}", "name": r["display_name"], "data": r["doc"]} for r in rows]}
