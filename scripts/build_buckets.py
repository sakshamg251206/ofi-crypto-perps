"""Build 1 s buckets (OFI, ΔMid, depth, spread, TI) for every non-test day of a symbol, in bounded memory.

Run: .venv/bin/python scripts/build_buckets.py [--symbol BTCUSDT]
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

from ofi.io import DATA_DIR, download_day, load_top_of_book, load_trades
from ofi.ofi import DAY_US, bucketize_chunks, drop_funding, resample_buckets, trade_imbalance
from ofi.quality import QualityAccumulator, infer_tick

ROOT = Path(__file__).resolve().parents[1]
DATASET, CHUNK_ROWS = "book_ticker", 5_000_000
DATES = [dt.date(y, m, 1).isoformat() for y in range(2023, 2027) for m in range(1, 13)
         if dt.date(2023, 9, 1) <= dt.date(y, m, 1) <= dt.date(2026, 3, 1)]


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
    assert day0 % DAY_US == 0

    reader = iter(load_top_of_book(DATASET, symbol, date, chunksize=CHUNK_ROWS))
    first = next(reader)
    tick = infer_tick(np.r_[first["bid_price"].dropna(), first["ask_price"].dropna()])
    acc = QualityAccumulator(tick)
    b = bucketize_chunks(tap(itertools.chain([first], reader), acc.update), freq_s=freq_s, tick=tick, day0=day0,
                         clock=clock)
    q = acc.report() | {"tick": tick}
    if q["off_grid_rows"] > 1e-4 * q["rows"]:  # a few real off-tick orders exist (DECISIONS.md)
        raise ValueError(f"{symbol} {date}: {q['off_grid_rows']} rows off the {tick} tick grid")
    return b, q, day0


def build_day(symbol: str, date: str) -> dict:
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
    qdir = ROOT / "reports" / "quality"
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{DATASET}_{symbol}_{date}.md").write_text(
        f"# Data quality — {DATASET} {symbol} {date}\n\n```json\n{json.dumps(q, indent=2)}\n```\n")
    return q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    symbol = ap.parse_args().symbol
    for date in DATES:
        if bucket_path(date, symbol).exists():
            print(f"{date} exists, skipping", flush=True)
            continue
        t = time.time()
        try:
            q = build_day(symbol, date)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            print(f"{symbol} {date} MISSING (404 at Tardis) — reported as missing, not replaced", flush=True)
            continue
        print(f"{symbol} {date} tick={q['tick']} rows={q['rows']:,} off_grid={q['off_grid_rows']} dups={q['duplicate_rows']:,} backwards={q['ts_backwards']} "
              f"crossed={q['crossed_or_locked']} max_gap={q['max_gap_s']:.1f}s {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
