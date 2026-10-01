"""Per-day data-quality report for a raw top-of-book file, computable chunk by chunk."""
import numpy as np
import pandas as pd

US = 1_000_000


class QualityAccumulator:
    """Feed consecutive row chunks of one file via `update`, then call `report`.

    Spread stats use rows without NaN. `duplicate_rows` counts rows identical to
    the previous row (a repeated state, which contributes e_n = 0).
    """

    def __init__(self, tick: float):
        self.tick = tick
        self.prev = None  # last row of the previous chunk
        self.hi_ts = None  # max timestamp seen so far
        self.rows = self.nan_rows = self.dups = self.backwards = self.crossed = self.off_grid = 0
        self.max_gap = 0
        self.prices, self.spreads, self.delays = [], [], []
        self.per_hour = np.zeros(24, dtype=np.int64)

    def update(self, chunk: pd.DataFrame) -> None:
        if chunk.empty:
            return
        ts = chunk["timestamp"].to_numpy()
        full = chunk if self.prev is None else pd.concat([self.prev, chunk])
        vals = full.to_numpy()
        same_as_prev = (vals[1:] == vals[:-1]).all(axis=1)
        self.dups += int(same_as_prev.sum())
        tsf = full["timestamp"].to_numpy()
        self.backwards += int((np.diff(tsf) < 0).sum())

        # Gaps above the max timestamp seen so far are exact; below it, earlier
        # chunks may already cover the time (only possible with out-of-order rows).
        if self.hi_ts is None:
            sts = np.sort(ts)
        else:
            sts = np.sort(np.append(ts[ts >= self.hi_ts], self.hi_ts))
        gaps = np.diff(sts)
        if len(gaps):
            self.max_gap = max(self.max_gap, int(gaps.max()))
        self.hi_ts = max(self.hi_ts or ts.max(), ts.max())

        ok = chunk.dropna()
        self.rows += len(chunk)
        self.nan_rows += int(chunk.isna().any(axis=1).sum())
        self.crossed += int((ok["bid_price"] >= ok["ask_price"]).sum())
        on_grid = lambda p: np.abs(p / self.tick - np.round(p / self.tick)) < 1e-6
        self.off_grid += int((~(on_grid(ok["bid_price"]) & on_grid(ok["ask_price"]))).sum())
        self.prices.append(np.unique(np.concatenate([ok["bid_price"], ok["ask_price"]])))
        self.spreads.append(np.round((ok["ask_price"] - ok["bid_price"]).to_numpy() / self.tick).astype(np.int32))
        self.delays.append((chunk["local_timestamp"] - chunk["timestamp"]).to_numpy() / 1000)
        self.per_hour += np.bincount((ts // (3600 * US)) % 24, minlength=24)
        self.prev = chunk.iloc[[-1]]

    def report(self) -> dict:
        prices = np.unique(np.concatenate(self.prices))
        spread = np.concatenate(self.spreads)
        delay = np.concatenate(self.delays)
        return {
            "rows": self.rows,
            "rows_with_nan": self.nan_rows,
            "duplicate_rows": self.dups,
            "ts_backwards": self.backwards,
            "crossed_or_locked": self.crossed,
            "off_grid_rows": self.off_grid,
            "inferred_tick": round(float(np.diff(prices).min()), 10) if len(prices) > 1 else float("nan"),
            "spread_ticks_p50_p99_max": [int(np.percentile(spread, 50)), int(np.percentile(spread, 99)),
                                         int(spread.max())],
            "frac_spread_1tick": float((spread == 1).mean()),
            "recv_delay_ms_p50": float(np.percentile(delay, 50)),
            "recv_delay_ms_p99": float(np.percentile(delay, 99)),
            "frac_recv_delay_negative": float((delay < 0).mean()),
            "max_gap_s": self.max_gap / US,
            "rows_per_hour": self.per_hour.tolist(),
        }


def quality_report(book: pd.DataFrame, tick: float) -> dict:
    """Quality report for a whole in-memory file."""
    acc = QualityAccumulator(tick)
    acc.update(book)
    return acc.report()


def infer_tick(prices: np.ndarray, min_on_grid: float = 0.9999) -> float:
    """Largest t in {1, 2, 5} x 10^k with >= `min_on_grid` of prices on the t grid.

    Tolerates rare off-grid prices (real off-tick orders exist, see DECISIONS.md).
    """
    prices = np.asarray(prices, float)
    for k in range(4, -9, -1):
        for m in (5, 2, 1):
            t = m * 10.0 ** k
            if t > prices.min():  # else price / t rounds to 0 and every price looks "on grid"
                continue
            x = prices / t
            if np.mean(np.abs(x - np.round(x)) < 1e-6) >= min_on_grid:
                return round(t, 12)
    raise ValueError("no tick found")
