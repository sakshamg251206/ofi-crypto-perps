import numpy as np
import pandas as pd
import pytest

from ofi.regress import nw_lags, window_regressions

S = 1_000_000
DAY0 = 1_693_526_400 * S


def synthetic(beta=0.5, n_days_buckets=8640, seed=0):
    """dmid = beta * ofi + noise, ofi ~ N(0,1), noise ~ N(0,1) -> true R^2 = 0.2 for beta=0.5."""
    rng = np.random.default_rng(seed)
    ofi = rng.standard_normal(n_days_buckets)
    dmid = beta * ofi + rng.standard_normal(n_days_buckets)
    idx = pd.Index(DAY0 + np.arange(n_days_buckets) * 10 * S, name="t")
    return pd.DataFrame({"ofi": ofi, "dmid_ticks": dmid}, index=idx)


def test_one_regression_per_30min_window():
    res = window_regressions(synthetic(), freq_s=10)
    assert len(res) == 48
    assert (res["n"] == 180).all()


def test_recovers_known_beta_and_r2():
    res = window_regressions(synthetic(), freq_s=10)
    assert res["beta"].median() == pytest.approx(0.5, abs=0.05)
    assert res["r2"].median() == pytest.approx(0.2, abs=0.05)
    assert (res["beta"] > 0).mean() > 0.95


def test_placebo_shift_collapses_r2():
    res = window_regressions(synthetic(), freq_s=10, shift=5)
    assert res["r2"].median() < 0.02


def test_windows_with_too_few_observations_are_skipped():
    b = synthetic().iloc[:190]  # one full window + 10 buckets of the next
    res = window_regressions(b, freq_s=10)
    assert len(res) == 1


def test_newey_west_lag_rule():
    assert nw_lags(180) == 4
    assert nw_lags(100) == 4
    assert nw_lags(1000) == 6
