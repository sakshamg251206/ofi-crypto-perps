"""Aggregate inference: day-block bootstrap and the H3 depth-scaling NLS fit."""
from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.optimize import least_squares


def block_bootstrap(df: pd.DataFrame, block_col: str, stat: Callable[[pd.DataFrame], float],
                    n: int = 10_000, seed: int = 20260930) -> np.ndarray:
    """Bootstrap draws of `stat` (scalar or 1-D array), resampling whole blocks (days) with replacement.

    Days are the independent unit here (sampled a month apart); windows within a
    day are correlated, so resampling windows would understate uncertainty.
    """
    rng = np.random.default_rng(seed)
    blocks = [np.flatnonzero(m) for m in (df[block_col].to_numpy() == b for b in df[block_col].unique())]
    draws = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), len(blocks))
        draws.append(stat(df.iloc[np.concatenate([blocks[j] for j in pick])]))
    return np.asarray(draws, dtype=float)


def percentile_ci(draws: np.ndarray, level: float = 0.95):
    """Percentile interval; for (n, k) draws returns arrays of k lower and upper bounds."""
    a = (1 - level) / 2
    lo, hi = np.quantile(draws, a, axis=0), np.quantile(draws, 1 - a, axis=0)
    return (float(lo), float(hi)) if np.ndim(lo) == 0 else (lo, hi)


def fit_depth_nls(beta: np.ndarray, depth: np.ndarray, Z: pd.DataFrame) -> dict:
    """Fit beta_w = exp(a + Z_w·gamma) * D_w^(-lam) by least squares on beta levels.

    Unlike log-log OLS this keeps windows with beta <= 0 (no selection on the outcome).
    Log-log OLS on beta > 0 is used only for starting values.
    """
    beta, logd, Zm = np.asarray(beta, float), np.log(np.asarray(depth, float)), Z.to_numpy(float)
    X = np.column_stack([np.ones_like(logd), Zm, -logd])
    pos = beta > 0
    p0 = np.linalg.lstsq(X[pos], np.log(beta[pos]), rcond=None)[0]

    res = least_squares(lambda p: np.exp(X @ p) - beta, p0, method="lm")
    p = res.x
    return {"a": p[0], "gamma": dict(zip(Z.columns, p[1:-1])), "lam": p[-1], "n": len(beta),
            "converged": bool(res.success)}
