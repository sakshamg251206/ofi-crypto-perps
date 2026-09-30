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


def test_xcols_selects_regressor():
    b = synthetic()
    b["ti"] = np.random.default_rng(9).standard_normal(len(b))  # unrelated to dmid
    res = window_regressions(b, freq_s=10, xcols=("ti",))
    assert res["r2"].median() < 0.03


def test_extra_nonlinear_term_raises_r2_when_relation_is_nonlinear():
    # For Gaussian OFI, corr(OFI, OFI|OFI|) ~ 0.92, so curvature must be strong to show up;
    # this checks a clear nonlinearity clears the H2 threshold of 0.02.
    b = synthetic()
    b["dmid_ticks"] = 0.5 * b["ofi"] + 1.0 * b["ofi"] * b["ofi"].abs() + np.random.default_rng(3).standard_normal(len(b))
    b["ofi_abs"] = b["ofi"] * b["ofi"].abs()
    lin = window_regressions(b, freq_s=10)["r2"].median()
    quad = window_regressions(b, freq_s=10, xcols=("ofi", "ofi_abs"))["r2"].median()
    assert quad - lin > 0.02


def test_window_features_depth_mean_and_wide_spread_share():
    from ofi.regress import window_features
    idx = pd.Index(DAY0 + np.arange(360) * 10 * S, name="t")  # two 30-min windows
    b = pd.DataFrame({"depth": np.r_[np.full(180, 2.0), np.full(180, 6.0)],
                      "spread_ticks": np.r_[np.ones(90), np.full(90, 2.0), np.ones(180)]}, index=idx)
    f = window_features(b, window_s=1800)
    assert f["depth_mean"].tolist() == [2.0, 6.0]
    assert f["frac_spread_gt1"].tolist() == [0.5, 0.0]
