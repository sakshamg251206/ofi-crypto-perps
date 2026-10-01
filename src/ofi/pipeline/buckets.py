"""Build 1 s buckets (OFI, ΔMid, depth, spread, TI) for every in-sample day of a symbol, in bounded memory.

Run: ofi buckets [--symbol BTCUSDT] [--dates 2023-09-01 ...]
Output: data/buckets/book_ticker/<SYMBOL>/<date>_1s.parquet, reports/quality/book_ticker_<SYMBOL>_<date>.md
"""
import argparse
import datetime as dt
import itertools
import json
import time
import urllib.error
from pathlib import Path

import numpy as np

from ofi.config import DATA_DIR, DATASET, DATES, REPORTS_DIR
from ofi.io import download_day, load_top_of_book, load_trades
from ofi.ofi import DAY_US, bucketize_chunks, drop_funding, resample_buckets, trade_imbalance
from ofi.quality import QualityAccumulator, infer_tick

CHUNK_ROWS = 5_000_000  # keeps peak memory near 3 GB on 50M-row days
MAX_OFF_GRID_SHARE = 1e-4  # a few real off-tick orders exist (docs/DECISIONS.md); more means a bad tick


def bucket_path(date: str, symbol: str = "BTCUSDT") -> Path:
    return DATA_DIR / "buckets" / DATASET / symbol / f"{date}_1s.parquet"


def tap(chunks, fn):
    """Yield chunks unchanged, calling fn on each (one pass feeds quality + buckets)."""
    for c in chunks:
        fn(c)
        yield c


def day_buckets(symbol: str, date: str, freq_s: float = 1, clock: str = "timestamp"):
    """Buckets + quality report for one day; tick inferred from the day's first chunk."""
    download_day(DATASET, symbol, date)
    day0 = int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC).timestamp()) * 1_000_000
    if day0 % DAY_US:
        raise ValueError(f"{date} is not a UTC midnight")

    reader = iter(load_top_of_book(DATASET, symbol, date, chunksize=CHUNK_ROWS))
    first = next(reader, None)
    if first is None or first.empty:
        raise ValueError(f"{symbol} {date}: empty {DATASET} file")
    tick = infer_tick(np.r_[first["bid_price"].dropna(), first["ask_price"].dropna()])
    acc = QualityAccumulator(tick)
    b = bucketize_chunks(tap(itertools.chain([first], reader), acc.update), freq_s=freq_s, tick=tick, day0=day0,
                         clock=clock)
    q = acc.report() | {"tick": tick}
    if q["off_grid_rows"] > MAX_OFF_GRID_SHARE * q["rows"]:
        raise ValueError(f"{symbol} {date}: {q['off_grid_rows']} rows off the {tick} tick grid")
    return b, q, day0


def build_day(symbol: str, date: str) -> dict:
    """Bucket one day, attach trade imbalance, write parquet + quality report; returns the quality dict."""
    download_day("trades", symbol, date)
    b, q, day0 = day_buckets(symbol, date)
    b["ti"] = trade_imbalance(load_trades(symbol, date), day0=day0, freq_s=1).to_numpy()
    b10 = drop_funding(resample_buckets(b, 10), 10)
    q |= {"frac_empty_1s_buckets": float((b["n_events"] == 0).mean()),
          "frac_dmid_zero_10s": float((b10["dmid_ticks"] == 0).mean()),
          "frac_spread_gt1_10s_bucket_end": float((b10["spread_ticks"] > 1).mean())}

    out = bucket_path(date, symbol)
    out.parent.mkdir(parents=True, exist_ok=True)
    b.to_parquet(out)
    qdir = REPORTS_DIR / "quality"
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{DATASET}_{symbol}_{date}.md").write_text(
        f"# Data quality — {DATASET} {symbol} {date}\n\n```json\n{json.dumps(q, indent=2)}\n```\n")
    return q


def add_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--symbol", default="BTCUSDT", help="Binance USDⓈ-M perp (default: %(default)s)")
    ap.add_argument("--dates", nargs="+", default=DATES, metavar="YYYY-MM-DD",
                    help="days to build (default: all 31 in-sample days)")


def run(args: argparse.Namespace) -> None:
    symbol = args.symbol
    for date in args.dates:
        if bucket_path(date, symbol).exists():
            print(f"{symbol} {date} exists, skipping", flush=True)
            continue
        t = time.time()
        try:
            q = build_day(symbol, date)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"{symbol} {date} MISSING (404 at Tardis) — reported as missing, not replaced", flush=True)
            continue
        print(f"{symbol} {date} tick={q['tick']} rows={q['rows']:,} off_grid={q['off_grid_rows']} "
              f"dups={q['duplicate_rows']:,} backwards={q['ts_backwards']} crossed={q['crossed_or_locked']} "
              f"max_gap={q['max_gap_s']:.1f}s {time.time() - t:.0f}s", flush=True)
