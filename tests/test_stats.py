import numpy as np
import pandas as pd
import pytest

from ofi.stats import block_bootstrap, fit_depth_nls, percentile_ci


def day_panel(n_days=30, per_day=48, seed=0):
    rng = np.random.default_rng(seed)
    day_means = rng.normal(0, 1, n_days)
    return pd.DataFrame({"day": np.repeat(np.arange(n_days), per_day),
                         "x": np.repeat(day_means, per_day) + rng.normal(0, 0.1, n_days * per_day)})


def test_bootstrap_resamples_whole_days():
    df = day_panel()
    sizes = block_bootstrap(df, "day", lambda d: len(d), n=200, seed=1)
    assert np.all(sizes % 48 == 0) and np.all(sizes == 30 * 48)


def test_bootstrap_is_reproducible_with_seed():
    df = day_panel()
    a = block_bootstrap(df, "day", lambda d: d["x"].mean(), n=100, seed=7)
    b = block_bootstrap(df, "day", lambda d: d["x"].mean(), n=100, seed=7)
    assert np.array_equal(a, b)


def test_bootstrap_ci_width_reflects_between_day_variation():
    # Day means vary with sd 1 across 30 days -> se of mean ~ 1/sqrt(30) ~ 0.18, not the tiny within-day 0.1/sqrt(1440).
    df = day_panel()
    lo, hi = percentile_ci(block_bootstrap(df, "day", lambda d: d["x"].mean(), n=2000, seed=2))
    assert 0.4 < hi - lo < 1.1


def synthetic_windows(lam=1.0, n=1500, seed=0):
    rng = np.random.default_rng(seed)
    depth = np.exp(rng.uniform(np.log(0.5), np.log(20), n))
    weekend = rng.integers(0, 2, n)
    block = rng.integers(0, 6, n)
    Z = pd.get_dummies(pd.Categorical(block), prefix="blk", drop_first=True).astype(float)
    Z["weekend"] = weekend
    beta = np.exp(0.3 + 0.2 * weekend + 0.1 * block) * depth ** (-lam) + rng.normal(0, 0.05, n)
    return beta, depth, Z


def test_nls_recovers_lambda_with_controls():
    beta, depth, Z = synthetic_windows(lam=1.0)
    fit = fit_depth_nls(beta, depth, Z)
    assert fit["lam"] == pytest.approx(1.0, abs=0.05)
    assert fit["gamma"]["weekend"] == pytest.approx(0.2, abs=0.05)


def test_nls_keeps_nonpositive_betas():
    beta, depth, Z = synthetic_windows(lam=1.0)
    assert (beta <= 0).any()
    assert fit_depth_nls(beta, depth, Z)["n"] == len(beta)


def test_bootstrap_supports_vector_statistics():
    df = day_panel()
    draws = block_bootstrap(df, "day", lambda d: np.array([d["x"].mean(), len(d)]), n=10, seed=0)
    assert draws.shape == (10, 2)
