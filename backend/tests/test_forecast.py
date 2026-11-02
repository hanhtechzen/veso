import numpy as np

from luckyvision.forecast.models import MODELS, counts_matrix, label, normalize, rank, run_model
from luckyvision.forecast.service import backtest, score_forecast, summarize

rng = np.random.default_rng(1)
XS = [[int(x) for x in rng.integers(0, 100, 27)] for _ in range(200)]
VL = [sorted(int(x) for x in rng.choice(np.arange(1, 56), 6, replace=False)) for _ in range(200)]


def test_every_model_runs_and_ranks_all_numbers():
    C = counts_matrix(XS, "xs")
    for m in MODELS:
        scores, probs, params = run_model(m.id, C, "mb", "seed")
        order = rank(scores)
        assert sorted(order) == list(range(100))
        assert (probs is not None) == m.probabilistic
        if probs is not None:
            assert ((probs > 0) & (probs < 1)).all()
        assert len(normalize(scores, order)) == 100


def test_power_universe_and_labels():
    C = counts_matrix(VL, "power655")
    assert C.shape == (200, 55) and C.sum() == 1200
    assert label("power655", 0) == "01" and label("xs", 7) == "07"
    scores, probs, _ = run_model("logreg", C, "vl", "s")
    assert len(scores) == 55


def test_not_enough_history():
    assert run_model("logreg", counts_matrix(XS[:10], "xs"), "mb", "s") is None
    assert run_model("freq", counts_matrix(XS[:2], "xs"), "mb", "s") is None


def test_random_model_is_reproducible():
    C = counts_matrix(XS, "xs")
    a = run_model("rand", C, "mb", "mb-mb-2026-10-29")[0]
    b = run_model("rand", C, "mb", "mb-mb-2026-10-29")[0]
    c = run_model("rand", C, "mb", "mb-mb-2026-10-30")[0]
    assert (a == b).all() and not (a == c).all()


def test_no_lookahead():
    """Thêm dữ liệu tương lai không được làm đổi dự báo của quá khứ."""
    C = counts_matrix(XS, "xs")
    for mid in ("freq", "roll", "dist", "logreg"):
        a = run_model(mid, C[:150], "mb", "s")[0]
        b = run_model(mid, counts_matrix(XS[:150], "xs"), "mb", "s")[0]
        assert np.allclose(a, b)


def test_score_and_summary():
    s = score_forecast("power655", ["09", "29", "33", "01", "02", "03"] + [f"{i:02d}" for i in range(4, 56) if i not in (9, 29, 33)],
                       None, {}, {9, 29, 33, 38, 45, 46})
    assert s["hits"] == {"6": 3} and s["baseline"] == {"6": round(6 * 6 / 55, 4)}
    r = summarize([{"hits": {"10": 3}, "baseline": {"10": 2.4}, "brier": None, "brier_uniform": None}] * 5, 10)
    assert r["n"] == 5 and r["precision"] == 0.3 and r["verdict"] == "insufficient"
    r = summarize([{"hits": {"10": 3}, "baseline": {"10": 2.4}, "brier": None, "brier_uniform": None}] * 30, 10)
    assert r["verdict"] == "better"


def test_backtest_random_data_finds_no_edge():
    res = backtest(XS, "xs", "mb", 120, 10)
    assert set(res) == {m.id for m in MODELS}
    assert all(abs(r["diff"]) < 0.08 for r in res.values() if r.get("n"))
