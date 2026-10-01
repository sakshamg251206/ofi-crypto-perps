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


def _chunk_aggregates(chunk, prev_row, day0, f, n_buckets, clock):
    """Per-bucket partial aggregates for one chunk; prev_row carries state across chunk edges."""
    if prev_row is None:
        e = compute_e(chunk).fillna(0.0).to_numpy()
    else:
        e = compute_e(pd.concat([prev_row, chunk])).to_numpy()[1:]
    k = (chunk[clock].to_numpy() - day0) // f
    parts = pd.DataFrame({
        "k": k, "e": e,
        "mid": ((chunk["bid_price"] + chunk["ask_price"]) / 2).to_numpy(),
        "depth": ((chunk["bid_amount"] + chunk["ask_amount"]) / 2).to_numpy(),
        "spread": ((chunk["ask_price"] - chunk["bid_price"])).to_numpy(),
    })
    before = parts[parts["k"] < 0]
    seed = before.iloc[-1] if len(before) else None
    agg = (parts[(parts["k"] >= 0) & (parts["k"] < n_buckets)].groupby("k")
           .agg(ofi=("e", "sum"), n_events=("e", "size"), mid=("mid", "last"),
                depth=("depth", "last"), spread=("spread", "last")))
    return agg, seed


def bucketize_chunks(chunks, freq_s: float, tick: float, day0: int, clock: str = "timestamp") -> pd.DataFrame:
    """Bucketize one UTC day streamed as consecutive row chunks (see `bucketize`)."""
    f = int(round(freq_s * US))
    n_buckets = DAY_US // f
    aggs, seed, prev_row = [], None, None
    for chunk in chunks:
        agg, s = _chunk_aggregates(chunk, prev_row, day0, f, n_buckets, clock)
        aggs.append(agg)
        seed = s if s is not None else seed
        prev_row = chunk.iloc[[-1]]
    agg = (pd.concat(aggs).groupby(level=0)
           .agg({"ofi": "sum", "n_events": "sum", "mid": "last", "depth": "last", "spread": "last"})
           .reindex(range(n_buckets)))
    seed_mid, seed_depth, seed_spread = (np.nan,) * 3 if seed is None else (seed["mid"], seed["depth"], seed["spread"])

    mid_end = agg["mid"].fillna({0: seed_mid}).ffill()
    mid_prev = mid_end.shift()
    mid_prev.iloc[0] = seed_mid
    return pd.DataFrame(
        {
            "ofi": agg["ofi"].fillna(0.0).to_numpy(),
            "dmid_ticks": np.round((mid_end - mid_prev).to_numpy() / tick, 9),
            "depth": agg["depth"].fillna({0: seed_depth}).ffill().to_numpy(),
            "spread_ticks": np.round(agg["spread"].fillna({0: seed_spread}).ffill().to_numpy() / tick, 9),
            "n_events": agg["n_events"].fillna(0).astype("int64").to_numpy(),
            "mid": mid_end.to_numpy(),
        },
        index=pd.Index(day0 + np.arange(n_buckets) * f, name="t"),
    )


def bucketize(book: pd.DataFrame, freq_s: float, tick: float, clock: str = "timestamp") -> pd.DataFrame:
    """Aggregate one UTC day of top-of-book updates into fixed buckets [t, t + freq).

    Returns one row per bucket over the whole day (index `t` = bucket start, µs):
      ofi          sum of e_n for updates in the bucket (0 if none)
      dmid_ticks   mid at bucket end minus mid at previous bucket end, in ticks
      depth        (bid size + ask size) / 2 of the book state at bucket end
      spread_ticks ask - bid of the book state at bucket end, in ticks
      n_events     number of updates in the bucket
      mid          mid of the book state at bucket end (price units; last update with clock < bucket end)
    Rows before the day (e.g. the file's pre-midnight row) only seed the
    starting state; their e_n are not counted.
    """
    day0 = (int(np.median(book[clock].to_numpy())) // DAY_US) * DAY_US
    return bucketize_chunks([book], freq_s, tick, day0, clock)


def resample_buckets(buckets: pd.DataFrame, freq_s: int) -> pd.DataFrame:
    """Coarsen buckets: flows and ΔMid sum (ΔMid telescopes), book state takes the last value.

    Note: a NaN ΔMid (no starting state) is treated as 0 in the sum.
    """
    f = freq_s * US
    how = {"ofi": "sum", "dmid_ticks": "sum", "depth": "last", "spread_ticks": "last", "n_events": "sum", "ti": "sum",
           "mid": "last"}
    out = buckets.groupby(buckets.index.to_numpy() // f * f).agg({c: how[c] for c in buckets.columns})
    out["dmid_ticks"] = out["dmid_ticks"].round(9)
    out.index.name = "t"
    return out


def trade_imbalance(trades: pd.DataFrame, day0: int, freq_s: float, clock: str = "timestamp") -> pd.Series:
    """TI_k = sum of signed trade size per bucket (+ taker buy, - taker sell); trades outside the day ignored."""
    f = int(round(freq_s * US))
    n_buckets = DAY_US // f
    k = (trades[clock].to_numpy() - day0) // f
    side = trades["side"].to_numpy()
    signed = ((side == "buy") * 1.0 - (side == "sell") * 1.0) * trades["amount"].to_numpy()  # "unknown" -> 0
    inday = (k >= 0) & (k < n_buckets)
    ti = np.bincount(k[inday], weights=signed[inday], minlength=n_buckets)
    return pd.Series(ti, index=pd.Index(day0 + np.arange(n_buckets) * f, name="t"), name="ti")


def overlaps_funding(start_us: np.ndarray, end_us: np.ndarray, minutes: int = 2) -> np.ndarray:
    """True where span [start, end) overlaps [F - minutes, F + minutes) for a funding time F (00/08/16 UTC).

    Assumes spans shorter than 8 h - 2*minutes, so only the previous and next funding times matter.
    """
    w = minutes * 60 * US
    s = np.asarray(start_us) % FUNDING_PERIOD_US
    e = s + (np.asarray(end_us) - np.asarray(start_us))
    return (s < w) | (e > FUNDING_PERIOD_US - w)


def drop_funding(buckets: pd.DataFrame, freq_s: int, minutes: int = 2) -> pd.DataFrame:
    """Drop buckets overlapping ±`minutes` around a funding time (00/08/16 UTC)."""
    t = buckets.index.to_numpy()
    return buckets[~overlaps_funding(t, t + int(round(freq_s * US)), minutes)]
