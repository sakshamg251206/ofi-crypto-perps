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
    buckets: pd.DataFrame, freq_s: int, window_s: int = 1800, shift: int = 0
) -> pd.DataFrame:
    """OLS of dmid_ticks on ofi within each window, with Newey–West t-stats.

    `shift` is the placebo: regress dmid at t on OFI from t - shift*freq
    (matched by time, so funding gaps don't misalign buckets). Windows with
    fewer than MIN_OBS usable buckets or constant OFI are skipped.
    """
    f = freq_s * US
    t = buckets.index.to_numpy()
    x = buckets["ofi"].reindex(t - shift * f).to_numpy() if shift else buckets["ofi"].to_numpy()
    df = pd.DataFrame({"y": buckets["dmid_ticks"].to_numpy(), "x": x, "w": t // (window_s * US) * (window_s * US)})
    df = df.dropna()

    rows = []
    for w, g in df.groupby("w"):
        if len(g) < MIN_OBS or g["x"].std() == 0:
            continue
        fit = sm.OLS(g["y"].to_numpy(), sm.add_constant(g["x"].to_numpy())).fit(
            cov_type="HAC", cov_kwds={"maxlags": nw_lags(len(g))}
        )
        rows.append({"window": w, "alpha": fit.params[0], "beta": fit.params[1],
                     "t_nw": fit.tvalues[1], "r2": fit.rsquared, "n": len(g)})
    return pd.DataFrame(rows).set_index("window") if rows else pd.DataFrame(
        columns=["alpha", "beta", "t_nw", "r2", "n"])
