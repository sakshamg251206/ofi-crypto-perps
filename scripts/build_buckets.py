"""Build 1 s buckets (OFI, ΔMid, depth, spread, TI) for every non-test BTCUSDT day, in bounded memory.

Run: .venv/bin/python scripts/build_buckets.py
Output: data/buckets/book_ticker/BTCUSDT/<date>_1s.parquet, reports/quality/<date>.md
"""
import datetime as dt
import json
import time
from pathlib import Path

from ofi.io import DATA_DIR, download_day, load_top_of_book, load_trades
from ofi.ofi import DAY_US, bucketize_chunks, drop_funding, resample_buckets, trade_imbalance
from ofi.quality import QualityAccumulator

ROOT = Path(__file__).resolve().parents[1]
SYMBOL, TICK, DATASET, CHUNK_ROWS = "BTCUSDT", 0.1, "book_ticker", 5_000_000
DATES = [dt.date(y, m, 1).isoformat() for y in range(2023, 2027) for m in range(1, 13)
         if dt.date(2023, 9, 1) <= dt.date(y, m, 1) <= dt.date(2026, 3, 1)]


def bucket_path(date: str) -> Path:
    return DATA_DIR / "buckets" / DATASET / SYMBOL / f"{date}_1s.parquet"


def tap(chunks, fn):
    """Yield chunks unchanged, calling fn on each (one pass feeds quality + buckets)."""
    for c in chunks:
        fn(c)
        yield c


def build_day(date: str) -> dict:
    for ds in (DATASET, "trades"):
        download_day(ds, SYMBOL, date)
    day0 = int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC).timestamp()) * 1_000_000
    assert day0 % DAY_US == 0

    acc = QualityAccumulator(TICK)
    chunks = tap(load_top_of_book(DATASET, SYMBOL, date, chunksize=CHUNK_ROWS), acc.update)
    b = bucketize_chunks(chunks, freq_s=1, tick=TICK, day0=day0)
    b["ti"] = trade_imbalance(load_trades(SYMBOL, date), day0=day0, freq_s=1).to_numpy()

    q = acc.report()
    if q["off_grid_rows"] > 1e-4 * q["rows"]:  # a few real off-tick orders exist (DECISIONS.md)
        raise ValueError(f"{date}: {q['off_grid_rows']} rows off the {TICK} tick grid")
    b10 = drop_funding(resample_buckets(b, 10), 10)
    q |= {"frac_empty_1s_buckets": float((b["n_events"] == 0).mean()),
          "frac_dmid_zero_10s": float((b10["dmid_ticks"] == 0).mean()),
          "frac_spread_gt1_10s_bucket_end": float((b10["spread_ticks"] > 1).mean())}

    out = bucket_path(date)
    out.parent.mkdir(parents=True, exist_ok=True)
    b.to_parquet(out)
    qdir = ROOT / "reports" / "quality"
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{DATASET}_{SYMBOL}_{date}.md").write_text(
        f"# Data quality — {DATASET} {SYMBOL} {date}\n\n```json\n{json.dumps(q, indent=2)}\n```\n")
    return q


def main() -> None:
    for date in DATES:
        if bucket_path(date).exists():
            print(f"{date} exists, skipping", flush=True)
            continue
        t = time.time()
        q = build_day(date)
        print(f"{date} rows={q['rows']:,} off_grid={q['off_grid_rows']} dups={q['duplicate_rows']:,} backwards={q['ts_backwards']} "
              f"crossed={q['crossed_or_locked']} max_gap={q['max_gap_s']:.1f}s {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
