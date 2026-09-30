"""Per-window CKS regressions: dmid_ticks = alpha + beta * ofi + eps."""
import math

import pandas as pd
import statsmodels.api as sm

US = 1_000_000
MIN_OBS = 30


def nw_lags(n: int) -> int:
    """Newey–West (1994) plug-in lag length: floor(4 (n/100)^(2/9))."""
    return math.floor(4 * (n / 100) ** (2 / 9))


def window_regressions(
    buckets: pd.DataFrame, freq_s: int, window_s: int = 1800, shift: int = 0,
    xcols: tuple[str, ...] = ("ofi",), y: str = "dmid_ticks",
) -> pd.DataFrame:
    """OLS of `y` on `xcols` (+ constant) within each window, with Newey–West t-stats.

    `beta`/`t_nw` refer to the first regressor. `shift` is the placebo: regress
    y at t on regressors from t - shift*freq (matched by time, so funding gaps
    don't misalign buckets). Windows with fewer than MIN_OBS usable buckets or a
    constant first regressor are skipped.
    """
    f = freq_s * US
    t = buckets.index.to_numpy()
    X = buckets[list(xcols)].reindex(t - shift * f) if shift else buckets[list(xcols)]
    df = pd.DataFrame(X.to_numpy(), columns=list(xcols))
    df["y"] = buckets[y].to_numpy()
    df["w"] = t // (window_s * US) * (window_s * US)
    df = df.dropna()

    rows = []
    for w, g in df.groupby("w"):
        if len(g) < MIN_OBS or g[xcols[0]].std() == 0:
            continue
        fit = sm.OLS(g["y"].to_numpy(), sm.add_constant(g[list(xcols)].to_numpy(), has_constant="add")).fit(
            cov_type="HAC", cov_kwds={"maxlags": nw_lags(len(g))}
        )
        rows.append({"window": w, "alpha": fit.params[0], "beta": fit.params[1],
                     "t_nw": fit.tvalues[1], "r2": fit.rsquared, "n": len(g)})
    return pd.DataFrame(rows).set_index("window") if rows else pd.DataFrame(
        columns=["alpha", "beta", "t_nw", "r2", "n"])


def window_features(buckets: pd.DataFrame, window_s: int = 1800) -> pd.DataFrame:
    """Per-window book state: D_w = mean bucket-end depth; share of bucket-end spreads > 1 tick."""
    w = buckets.index.to_numpy() // (window_s * US) * (window_s * US)
    g = buckets.assign(gt1=buckets["spread_ticks"] > 1).groupby(w)
    out = pd.DataFrame({"depth_mean": g["depth"].mean(), "frac_spread_gt1": g["gt1"].mean()})
    out.index.name = "window"
    return out
