from luckyvision.forecast.probabilities import calibration_bins, theory_prob, wilson


def test_theory():
    assert round(theory_prob("xs", 27), 4) == 0.2377
    assert round(theory_prob("xs", 18), 4) == 0.1655
    assert round(theory_prob("power655", 6), 4) == round(6 / 55, 4)


def test_wilson_contains_true_rate_and_shrinks():
    lo, hi = wilson(24, 100)
    assert lo < 0.24 < hi
    lo2, hi2 = wilson(240, 1000)
    assert hi2 - lo2 < hi - lo
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(0, 10)[0] == 0.0


def test_calibration_bins_equal_count_and_merge_tail():
    pairs = [(i / 100, 1 if i % 4 == 0 else 0) for i in range(105)]
    b = calibration_bins(pairs, 10)
    assert sum(x["count"] for x in b) == 105
    assert all(b[i]["predicted"] <= b[i + 1]["predicted"] for i in range(len(b) - 1))
    assert len(b) == 10
    assert calibration_bins([], 10) == []
