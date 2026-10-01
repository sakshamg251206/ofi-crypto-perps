"""H5/H6: predictive OFI on the receive clock, out-of-sample R², and a sign strategy net of costs.

Timing (DECISIONS.md, 2026-10-01): x_k = OFI over [t_{k-1}, t_k); y_k = mid(t_{k+1}+L) - mid(t_k+L).
"""
import numpy as np
import pandas as pd

from ofi.ofi import overlaps_funding

US = 1_000_000


def predictive_frame(b100: pd.DataFrame, tick: float, freq_s: int = 10,
                     latencies_ms: tuple[int, ...] = (0, 100, 500)) -> pd.DataFrame:
    """One row per decision time t_k from 100 ms receive-clock buckets of one day.

    b100 must cover the whole day (index = bucket start, µs) with columns ofi, ti, mid, depth, spread_ticks.
    mid(T) = book state at the end of the 100 ms bucket ending at T (last update received before T).
    """
    step = 100_000
    f = freq_s * US
    per = f // step
    day0 = int(b100.index[0])
    n = len(b100) // per  # decision buckets in the day

    ofi10 = b100["ofi"].to_numpy().reshape(n, per).sum(axis=1)
    ti10 = b100["ti"].to_numpy().reshape(n, per).sum(axis=1)
    mid, depth, spread = (b100[c].to_numpy() for c in ("mid", "depth", "spread_ticks"))

    def state_at(arr, T):  # value at the end of the 100 ms bucket ending at T
        return arr[(T - day0) // step - 1]

    k = np.arange(1, n - 1)  # need [t_{k-1}, t_k) and t_{k+1} inside the day
    t = day0 + k * f
    out = pd.DataFrame(index=pd.Index(t, name="t"))
    out["x"] = ofi10[k - 1]
    out["ti_lag"] = ti10[k - 1]
    out["ar_lag"] = (state_at(mid, t) - state_at(mid, t - f)) / tick
    out["depth_t"] = state_at(depth, t)
    out["feat_start"], out["feat_end"] = t - f, t
    for L in latencies_ms:
        lu = L * 1000
        m0, m1 = state_at(mid, t + lu), state_at(mid, t + f + lu)
        out[f"y_{L}"] = np.round((m1 - m0) / tick, 9)
        out[f"mid_entry_{L}"] = m0
        out[f"half_spread_bps_{L}"] = state_at(spread, t + lu) * tick / 2 / m0 * 1e4
        out[f"tgt_start_{L}"], out[f"tgt_end_{L}"] = t + lu, t + f + lu
    span_end = t + f + max(latencies_ms) * 1000
    return out[~overlaps_funding(t - f, span_end)].dropna()


def fit_ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Intercept and slope of y = a + b x by least squares."""
    X = np.column_stack([np.ones_like(x), x])
    a, b = np.linalg.lstsq(X, y, rcond=None)[0]
    return float(a), float(b)


def oos_r2(y: np.ndarray, yhat: np.ndarray) -> float:
    """Out-of-sample R² against the zero forecast (random walk): 1 - SSE / sum(y²)."""
    return float(1 - np.sum((y - yhat) ** 2) / np.sum(y ** 2))


def sign_strategy_pnl(df: pd.DataFrame, tick: float, fee_bps: float, freq_s: int = 10) -> dict:
    """Hold sign(yhat) for one bucket at each decision time; costs per unit of turnover.

    df: index t (µs), columns y (ticks), yhat, mid_entry, half_spread_bps. Positions run over
    contiguous decision times and are closed at gaps (funding exclusions, day ends). Each unit
    of turnover (|Δposition|) pays fee_bps + the half spread at that time.
    """
    p = np.sign(df["yhat"].to_numpy())
    gross = p * df["y"].to_numpy() * tick / df["mid_entry"].to_numpy() * 1e4
    t = df.index.to_numpy()
    new_seg = np.r_[True, np.diff(t) != freq_s * US]
    seg = np.cumsum(new_seg)
    prev = np.where(new_seg, 0.0, np.r_[0.0, p[:-1]])
    open_turn = np.abs(p - prev)
    last_in_seg = np.r_[seg[1:] != seg[:-1], True]
    close_turn = np.where(last_in_seg, np.abs(p), 0.0)
    turn = open_turn + close_turn
    cost = turn * (fee_bps + df["half_spread_bps"].to_numpy())
    total_turn = float(turn.sum())
    return {"gross_bps": float(gross.sum()), "turnover": total_turn, "net_bps": float(gross.sum() - cost.sum()),
            "break_even_bps": float(gross.sum() / total_turn) if total_turn else float("nan"),
            "gross_bps_per_bucket": float(gross.mean()), "buckets": len(df)}
