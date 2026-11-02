"""API dự báo: /v1/models, /v1/forecasts, /v1/forecasts/next, /v1/forecasts/performance."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request, Response

from ..forecast.models import MODELS
from ..forecast.service import K_VALUES, summarize
from .errors import ApiError
from .serialize import iso

router = APIRouter(prefix="/v1", tags=["forecasts"])
DISCLAIMER = ("Dự báo thống kê để tham khảo. Điểm xếp hạng không phải xác suất trúng; "
              "không mô hình nào được chứng minh tốt hơn chọn ngẫu nhiên.")


@router.get("/models")
async def models():
    return {"items": [{"id": m.id, "version": m.version, "name": m.name, "description": m.description,
                       "probabilistic": m.probabilistic} for m in MODELS], "disclaimer": DISCLAIMER}


def _forecast_json(f: dict, top: int) -> dict:
    out = {"id": f["id"], "draw_id": f["draw_id"], "model": f["model"], "version": f["version"],
           "created_at": iso(f["created_at"]),
           "input": {"from": f["window_from"].isoformat() if f["window_from"] else None,
                     "to": f["window_to"].isoformat() if f["window_to"] else None, "draws": f["window_n"]},
           "ranking": [{"number": n, "score": s} for n, s in zip(f["ranking"][:top], f["scores"][:top])]}
    if f.get("hits") is not None:
        out["evaluation"] = {"hits": f["hits"], "baseline": f["baseline"], "brier": f["brier"],
                             "brier_uniform": f["brier_uniform"]}
    return out


async def _forecasts_for(conn, draw_ids: list[str], top: int) -> dict[str, list[dict]]:
    rows = await (await conn.execute(
        """SELECT f.*, e.hits, e.baseline, e.brier, e.brier_uniform FROM forecasts f
             LEFT JOIN forecast_evaluations e ON e.forecast_id = f.id
            WHERE f.draw_id = ANY(%s) ORDER BY f.draw_id, f.model""", (draw_ids,))).fetchall()
    out: dict[str, list[dict]] = {}
    order = {m.id: i for i, m in enumerate(MODELS)}
    for r in sorted(rows, key=lambda r: order.get(r["model"], 99)):
        out.setdefault(r["draw_id"], []).append(_forecast_json(r, top))
    return out


def _draw_head(d: dict) -> dict:
    return {"id": d["id"], "region": d["region_code"], "province": {"code": d["province_code"], "name": d.get("pname")},
            "draw_date": d["draw_date"].isoformat(), "draw_time": iso(d["scheduled_at"]), "status": d["status"]}


@router.get("/forecasts")
async def list_forecasts(request: Request, response: Response, draw_id: str | None = None, region: str | None = None,
                         province: str | None = None, date_: date | None = Query(None, alias="date"),
                         top: int = Query(20, ge=1, le=100), limit: int = Query(10, ge=1, le=50)):
    q, args = ["SELECT d.*, p.name AS pname FROM lottery_draws d JOIN provinces p ON p.code = d.province_code "
               "WHERE EXISTS (SELECT 1 FROM forecasts f WHERE f.draw_id = d.id)"], []
    for cond, v in (("d.id = %s", draw_id), ("d.region_code = %s", region), ("d.province_code = %s", province),
                    ("d.draw_date = %s", date_)):
        if v is not None:
            q.append("AND " + cond); args.append(v)
    q.append("ORDER BY d.draw_date DESC, d.id LIMIT %s"); args.append(limit)
    async with request.app.state.pool.connection() as conn:
        draws = await (await conn.execute(" ".join(q), args)).fetchall()
        fc = await _forecasts_for(conn, [d["id"] for d in draws], top)
    response.headers["Cache-Control"] = "public, max-age=60"
    return {"items": [{"draw": _draw_head(d), "forecasts": fc.get(d["id"], [])} for d in draws],
            "disclaimer": DISCLAIMER}


@router.get("/forecasts/next")
async def next_forecasts(request: Request, response: Response, region: str, province: str | None = None,
                         top: int = Query(20, ge=1, le=100)):
    q = ["""SELECT d.*, p.name AS pname FROM lottery_draws d JOIN provinces p ON p.code = d.province_code
             WHERE d.region_code = %s AND d.current_version IS NULL AND d.scheduled_at > now() - interval '1 hour'"""]
    args: list = [region]
    if province:
        q.append("AND d.province_code = %s"); args.append(province)
    q.append("ORDER BY d.scheduled_at, d.id LIMIT 6")
    async with request.app.state.pool.connection() as conn:
        draws = await (await conn.execute(" ".join(q), args)).fetchall()
        if draws:
            first = draws[0]["draw_date"]
            draws = [d for d in draws if d["draw_date"] == first]
        fc = await _forecasts_for(conn, [d["id"] for d in draws], top)
    response.headers["Cache-Control"] = "public, max-age=60"
    return {"items": [{"draw": _draw_head(d), "forecasts": fc.get(d["id"], [])} for d in draws],
            "disclaimer": DISCLAIMER}


@router.get("/forecasts/performance")
async def performance(request: Request, response: Response, region: str, province: str | None = None,
                      k: int | None = None, days: int = Query(365, ge=7, le=3650)):
    game = "power655" if region == "vl" else "xs"
    k = k or K_VALUES[game][min(1, len(K_VALUES[game]) - 1)]
    if str(k) not in {str(x) for x in K_VALUES[game]}:
        raise ApiError(400, "invalid_param", f"k phải là một trong {K_VALUES[game]}")
    q = ["""SELECT f.model, e.hits, e.baseline, e.brier, e.brier_uniform FROM forecast_evaluations e
              JOIN forecasts f ON f.id = e.forecast_id JOIN lottery_draws d ON d.id = f.draw_id
             WHERE d.region_code = %s AND d.draw_date >= current_date - %s"""]
    args: list = [region, days]
    if province:
        q.append("AND d.province_code = %s"); args.append(province)
    async with request.app.state.pool.connection() as conn:
        rows = await (await conn.execute(" ".join(q), args)).fetchall()
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["model"], []).append(r)
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"region": region, "province": province, "k": k, "days": days,
            "items": [{"model": m.id, "name": m.name, "version": m.version, **summarize(by.get(m.id, []), k)}
                      for m in MODELS],
            "note": "Chỉ tính các dự báo đã công bố trước giờ quay và đã được chấm bằng kết quả thật."}


@router.get("/probabilities")
async def probabilities(request: Request, response: Response, region: str, province: str | None = None,
                        days: int = Query(365, ge=0, le=3650)):
    """Xác suất từng số: lý thuyết, tần suất lịch sử kèm khoảng tin cậy 95%, ước lượng mô hình cho kỳ tới."""
    from ..forecast.probabilities import default_province, number_probabilities
    province = province or default_province(region)
    if not province:
        raise ApiError(400, "invalid_param", "Cần chọn tỉnh/đài (province) cho miền này")
    async with request.app.state.pool.connection() as conn:
        out = await number_probabilities(conn, region, province, days)
    response.headers["Cache-Control"] = "public, max-age=300"
    out["note"] = ("Xác suất lý thuyết là mức thật khi kết quả hoàn toàn ngẫu nhiên. Tần suất lịch sử nằm trong khoảng tin cậy "
                   "nghĩa là chênh lệch chỉ do ngẫu nhiên. Ước lượng của mô hình không phải xác suất trúng đã được kiểm chứng.")
    return out


@router.get("/forecasts/calibration")
async def calibration_view(request: Request, response: Response, region: str, model: str = "logreg",
                           province: str | None = None, days: int = Query(365, ge=7, le=3650),
                           source: str = Query("auto", pattern="^(auto|published|backtest)$")):
    """Độ tin cậy: khi mô hình nói X%, thực tế số đó về bao nhiêu %.

    source=published: chỉ dùng dự báo đã công bố trước giờ quay. source=backtest: kiểm thử lùi 120 kỳ gần nhất.
    auto: dùng dự báo đã công bố nếu đã có từ 20 kỳ, nếu chưa thì kiểm thử lùi.
    """
    from ..forecast.probabilities import calibration, calibration_backtest, default_province
    if model not in ("dist", "logreg"):
        raise ApiError(400, "invalid_param", "Chỉ mô hình dist và logreg có ước lượng xác suất")
    province = province or default_province(region)
    async with request.app.state.pool.connection() as conn:
        out = None
        if source in ("auto", "published"):
            out = await calibration(conn, region, province, model, days)
            out["source"] = "published"
        if source == "backtest" or (source == "auto" and out["forecasts"] < 20):
            if not province:
                raise ApiError(400, "invalid_param", "Cần chọn tỉnh/đài (province) cho miền này")
            out = await calibration_backtest(conn, region, province, model)
    response.headers["Cache-Control"] = "public, max-age=300"
    return out
