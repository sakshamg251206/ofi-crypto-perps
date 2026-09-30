"""Per-day data-quality report for a raw top-of-book file."""
import numpy as np
import pandas as pd

US = 1_000_000


def quality_report(book: pd.DataFrame, tick: float) -> dict:
    """Raw-file sanity checks. Spread stats use rows without NaN."""
    ts = book["timestamp"].to_numpy()
    ok = book.dropna()
    prices = np.unique(np.concatenate([ok["bid_price"], ok["ask_price"]]))
    spread_ticks = np.round((ok["ask_price"] - ok["bid_price"]).to_numpy() / tick).astype(int)
    delay_ms = (book["local_timestamp"] - book["timestamp"]).to_numpy() / 1000
    hour = (ts // (3600 * US)) % 24

    return {
        "rows": len(book),
        "rows_with_nan": int(book.isna().any(axis=1).sum()),
        "duplicate_rows": int(book.duplicated().sum()),
        "ts_backwards": int((np.diff(ts) < 0).sum()),
        "crossed_or_locked": int((ok["bid_price"] >= ok["ask_price"]).sum()),
        "inferred_tick": round(float(np.diff(prices).min()), 10) if len(prices) > 1 else float("nan"),
        "spread_ticks_p50_p99_max": [int(np.percentile(spread_ticks, 50)), int(np.percentile(spread_ticks, 99)),
                                     int(spread_ticks.max())],
        "frac_spread_1tick": float((spread_ticks == 1).mean()),
        "recv_delay_ms_p50": float(np.percentile(delay_ms, 50)),
        "recv_delay_ms_p99": float(np.percentile(delay_ms, 99)),
        "frac_recv_delay_negative": float((delay_ms < 0).mean()),
        "max_gap_s": float(np.diff(np.sort(ts)).max() / US),
        "rows_per_hour": np.bincount(hour, minlength=24).tolist(),
    }
