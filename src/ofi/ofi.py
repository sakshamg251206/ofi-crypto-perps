"""Order-flow imbalance per Cont, Kukanov & Stoikov (2014)."""
import numpy as np
import pandas as pd

US = 1_000_000            # microseconds per second
DAY_US = 86_400 * US
FUNDING_PERIOD_US = 8 * 3600 * US  # Binance funding at 00:00, 08:00, 16:00 UTC


def compute_e(book: pd.DataFrame) -> pd.Series:
    """Per-update order-flow contribution e_n from consecutive best bid/ask states.

    e_n =  1{Pb_n >= Pb_{n-1}} qb_n - 1{Pb_n <= Pb_{n-1}} qb_{n-1}
         - 1{Pa_n <= Pa_{n-1}} qa_n + 1{Pa_n >= Pa_{n-1}} qa_{n-1}

    Bid side: a higher-or-equal bid adds its new size (buy pressure); a
    lower-or-equal bid removes the old size. At an unchanged price both fire,
    leaving the net size change. The ask side mirrors this with opposite sign.
    The first row has no predecessor and is NaN.
    """
    pb, qb = book["bid_price"], book["bid_amount"]
    pa, qa = book["ask_price"], book["ask_amount"]
    pb0, qb0, pa0, qa0 = pb.shift(), qb.shift(), pa.shift(), qa.shift()

    e = (
        (pb >= pb0) * qb - (pb <= pb0) * qb0
        - (pa <= pa0) * qa + (pa >= pa0) * qa0
    )
    e.iloc[0] = float("nan")
    return e


def bucketize(book: pd.DataFrame, freq_s: int, tick: float, clock: str = "timestamp") -> pd.DataFrame:
    """Aggregate one UTC day of top-of-book updates into fixed buckets [t, t + freq).

    Returns one row per bucket over the whole day (index `t` = bucket start, µs):
      ofi        sum of e_n for updates in the bucket (0 if none)
      dmid_ticks mid at bucket end minus mid at previous bucket end, in ticks
      depth      (bid size + ask size) / 2 of the book state at bucket end
      n_events   number of updates in the bucket
    Rows before the day (e.g. the file's pre-midnight row) only seed the
    starting state; their e_n are not counted.
    """
    f = freq_s * US
    ts = book[clock].to_numpy()
    day0 = (int(np.median(ts)) // DAY_US) * DAY_US
    n_buckets = DAY_US // f
    k = (ts - day0) // f
    inday = (k >= 0) & (k < n_buckets)
    before = k < 0

    mid = ((book["bid_price"] + book["ask_price"]) / 2).to_numpy()
    depth = ((book["bid_amount"] + book["ask_amount"]) / 2).to_numpy()
    e = compute_e(book).fillna(0.0).to_numpy()

    agg = (
        pd.DataFrame({"k": k[inday], "e": e[inday], "mid": mid[inday], "depth": depth[inday]})
        .groupby("k")
        .agg(ofi=("e", "sum"), n_events=("e", "size"), mid=("mid", "last"), depth=("depth", "last"))
        .reindex(range(n_buckets))
    )
    seed_mid = mid[before][-1] if before.any() else np.nan
    seed_depth = depth[before][-1] if before.any() else np.nan

    mid_end = agg["mid"].fillna({0: seed_mid}).ffill()
    mid_prev = mid_end.shift()
    mid_prev.iloc[0] = seed_mid

    out = pd.DataFrame(
        {
            "ofi": agg["ofi"].fillna(0.0).to_numpy(),
            "dmid_ticks": np.round((mid_end - mid_prev).to_numpy() / tick, 9),
            "depth": agg["depth"].fillna({0: seed_depth}).ffill().to_numpy(),
            "n_events": agg["n_events"].fillna(0).astype("int64").to_numpy(),
        },
        index=pd.Index(day0 + np.arange(n_buckets) * f, name="t"),
    )
    return out


def drop_funding(buckets: pd.DataFrame, freq_s: int, minutes: int = 2) -> pd.DataFrame:
    """Drop buckets overlapping ±`minutes` around a funding time (00/08/16 UTC)."""
    f, w = freq_s * US, minutes * 60 * US
    since_funding = buckets.index.to_numpy() % FUNDING_PERIOD_US
    keep = (since_funding >= w) & (since_funding + f <= FUNDING_PERIOD_US - w)
    return buckets[keep]
