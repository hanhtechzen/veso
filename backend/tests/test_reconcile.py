from luckyvision.domain.reconcile import Candidate, diff, reconcile

A = {"db": ["111111"], "g8": ["12"]}
B = {"db": ["111112"], "g8": ["12"]}


def c(i, src, payload, complete=True, prio=10, cs=None):
    return Candidate(i, src, prio, cs or str(sorted(payload.items())), complete, payload)


def test_two_sources_match_verified_and_pick_priority():
    d = reconcile([c(1, "b", A, prio=20), c(2, "a", A, prio=10)])
    assert d.outcome == "verified" and d.candidate_id == 2 and d.sources == ["a", "b"]


def test_single_source_waits():
    assert reconcile([c(1, "a", A)]).outcome == "waiting"


def test_incomplete_ignored():
    assert reconcile([c(1, "a", A), c(2, "b", A, complete=False)]).outcome == "waiting"


def test_conflict_reports_differences():
    d = reconcile([c(1, "a", A), c(2, "b", B, prio=20)])
    assert d.outcome == "conflict"
    assert d.differences == [{"prize": "db", "position": 0, "a": "111111", "b": "111112"}]


def test_latest_per_source_counts():
    # nguồn b sửa lại cho khớp a ở lần tải sau
    d = reconcile([c(1, "a", A), c(2, "b", B, prio=20), c(3, "b", A, prio=20)])
    assert d.outcome == "verified"


def test_manual_not_counted_as_source():
    assert reconcile([c(1, "a", A), c(2, "manual", A, prio=1)]).outcome == "waiting"


def test_diff_handles_length():
    assert diff({"g6": ["1", "2"]}, {"g6": ["1"]}) == [{"prize": "g6", "position": 1, "a": "2", "b": None}]
