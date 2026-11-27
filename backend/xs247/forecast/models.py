"""Các mô hình dự báo (mục F24–F30 của PRD).

Mọi mô hình chỉ nhìn các kỳ TRƯỚC kỳ cần dự báo (không rò rỉ dữ liệu) và trả về điểm cho từng số:
  - Xổ số truyền thống: 100 số lô 00–99 (hai chữ số cuối của mọi giải).
  - Power 6/55: 55 số 01–55 (chỉ bộ số chính).
Điểm là thứ hạng tương đối, KHÔNG phải xác suất trúng. Chỉ 'dist' và 'logreg' có ước lượng xác suất.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from ..domain.games import GAMES


@dataclass(frozen=True)
class ModelInfo:
    id: str
    version: str
    name: str
    description: str
    probabilistic: bool = False


MODELS: list[ModelInfo] = [
    ModelInfo("freq", "1.0", "Tần suất gần đây", "Đếm số lần mỗi số về trong W kỳ gần nhất của đài."),
    ModelInfo("roll", "1.0", "Cửa sổ trượt có trọng số",
              "Đếm số lần về của mọi kỳ trước, kỳ càng xa càng ít trọng số (giảm một nửa sau H kỳ)."),
    ModelInfo("dist", "1.0", "Phân phối lịch sử",
              "Tỉ lệ mỗi số có về trong một kỳ trên toàn bộ lịch sử, làm trơn về mức trung bình chung.", True),
    ModelInfo("logreg", "1.0", "Học máy: hồi quy logistic",
              "Học từ 4 đặc trưng của mỗi số (tần suất ngắn hạn, dài hạn, số kỳ chưa về, tỉ lệ lịch sử) "
              "trên tối đa 300 kỳ gần nhất, ước lượng xác suất số đó về ở kỳ tới.", True),
    ModelInfo("rand", "1.0", "Ngẫu nhiên (mốc so sánh)",
              "Xáo trộn ngẫu nhiên với hạt giống cố định theo mã kỳ quay, ai cũng tái lập được."),
]
MODEL_IDS = [m.id for m in MODELS]

REGION_PARAMS = {
    "mb": {"W": 30, "H": 20, "S": 7, "alpha": 30},
    "mn": {"W": 8, "H": 6, "S": 4, "alpha": 30},
    "mt": {"W": 8, "H": 6, "S": 4, "alpha": 30},
    "vl": {"W": 30, "H": 20, "S": 7, "alpha": 30},
    "mega": {"W": 30, "H": 20, "S": 7, "alpha": 30},
}
MIN_HISTORY = {"freq": 4, "roll": 4, "dist": 4, "logreg": 40, "rand": 0}


def universe(game: str) -> tuple[int, int]:
    """(số lượng số, số nhỏ nhất)."""
    return (GAMES[game].main_max, 1) if game in GAMES else (100, 0)


def label(game: str, idx: int) -> str:
    size, lo = universe(game)
    return f"{idx + lo:02d}"


def counts_matrix(draws: list[list[int]], game: str) -> np.ndarray:
    """Ma trận T x U: số lần mỗi số xuất hiện trong từng kỳ."""
    size, lo = universe(game)
    m = np.zeros((len(draws), size), dtype=np.float64)
    for t, nums in enumerate(draws):
        for n in nums:
            if lo <= n < lo + size:
                m[t, n - lo] += 1
    return m


def _seed(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def _gaps(C: np.ndarray) -> np.ndarray:
    """gaps[t, i]: số kỳ liên tiếp số i chưa về, tính trước kỳ t."""
    T, U = C.shape
    g = np.zeros((T + 1, U))
    cur = np.zeros(U)
    for t in range(T):
        g[t] = cur
        cur = np.where(C[t] > 0, 0, cur + 1)
    g[T] = cur
    return g


def _features(C: np.ndarray, t: int, gaps: np.ndarray, p: dict) -> np.ndarray:
    A = (C[:t] > 0)
    short = A[max(0, t - p["S"]):t].mean(0) if t else np.zeros(C.shape[1])
    long = A[max(0, t - p["W"]):t].mean(0) if t else np.zeros(C.shape[1])
    hist = A.mean(0) if t else np.zeros(C.shape[1])
    gap = np.log1p(gaps[t]) / 5.0
    return np.column_stack([short, long, gap, hist])


def _logreg(C: np.ndarray, p: dict, max_train: int = 300, iters: int = 250, lr: float = 0.5, l2: float = 1e-3):
    T, U = C.shape
    start = max(p["W"], T - max_train)
    if T - start < 20:
        return None
    gaps = _gaps(C)
    X = np.vstack([_features(C, t, gaps, p) for t in range(start, T)])
    y = np.concatenate([(C[t] > 0).astype(float) for t in range(start, T)])
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    w = np.zeros(Xs.shape[1])
    for _ in range(iters):
        z = np.clip(Xs @ w, -30, 30)
        pr = 1 / (1 + np.exp(-z))
        grad = Xs.T @ (pr - y) / len(y) + l2 * np.r_[0, w[1:]]
        w -= lr * grad
    xt = np.column_stack([np.ones(U), (_features(C, T, gaps, p) - mu) / sd])
    return 1 / (1 + np.exp(-np.clip(xt @ w, -30, 30)))


def run_model(model: str, C: np.ndarray, region: str, seed_key: str) -> tuple[np.ndarray, np.ndarray | None, dict] | None:
    """Trả về (điểm, xác suất hoặc None, tham số) hoặc None nếu chưa đủ dữ liệu."""
    p = REGION_PARAMS.get(region, REGION_PARAMS["mb"])
    T, U = C.shape
    if T < MIN_HISTORY[model]:
        return None
    A = (C > 0)
    q = float(A.mean()) if T else 0.0
    if model == "freq":
        return C[-p["W"]:].sum(0), None, {"W": p["W"]}
    if model == "roll":
        lam = 0.5 ** (1 / p["H"])
        w = lam ** np.arange(T - 1, -1, -1)
        return (C * w[:, None]).sum(0), None, {"H": p["H"]}
    if model == "dist":
        probs = (A.sum(0) + p["alpha"] * q) / (T + p["alpha"])
        return probs.copy(), probs, {"alpha": p["alpha"], "q": q}
    if model == "logreg":
        probs = _logreg(C, p)
        if probs is None:
            return None
        return probs.copy(), probs, {"S": p["S"], "W": p["W"], "q": q, "train_draws": min(300, T - p["W"])}
    if model == "rand":
        rng = np.random.default_rng(_seed(seed_key))
        return rng.permutation(U).astype(float), None, {"seed": seed_key}
    raise ValueError(model)


def rank(scores: np.ndarray) -> list[int]:
    """Chỉ số các số, điểm cao trước; bằng điểm thì số nhỏ trước."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


def normalize(scores: np.ndarray, order: list[int]) -> list[int]:
    lo, hi = float(scores.min()), float(scores.max())
    return [0 if hi == lo else round((float(scores[i]) - lo) / (hi - lo) * 100) for i in order]
