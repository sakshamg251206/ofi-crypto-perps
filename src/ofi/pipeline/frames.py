"""Per-day H5/H6 frames on the receive clock (docs/DECISIONS.md, 2026-10-01): x = OFI over [t_{k-1}, t_k),
y_L = mid(t_{k+1}+L) - mid(t_k+L), for L in {0, 100, 500} ms. Non-test days only (loader guard).

Run: ofi frames [--symbols BTCUSDT ETHUSDT WLDUSDT] [--dates ...]
Output: data/predict/<SYMBOL>/<date>.parquet
"""
import argparse
import time

from ofi.config import DATA_DIR, DATES, SYMBOLS
from ofi.io import download_day, load_trades
from ofi.ofi import trade_imbalance
from ofi.pipeline.buckets import day_buckets
from ofi.predict import predictive_frame


def frame_path(symbol: str, date: str):
    return DATA_DIR / "predict" / symbol / f"{date}.parquet"


def build_frame(symbol: str, date: str):
    download_day("trades", symbol, date)  # day_buckets only fetches book_ticker
    b, q, day0 = day_buckets(symbol, date, freq_s=0.1, clock="local_timestamp")
    if q["local_ts_backwards"]:
        raise ValueError(f"{symbol} {date}: receive clock goes backwards {q['local_ts_backwards']} times")
    b["ti"] = trade_imbalance(load_trades(symbol, date), day0=day0, freq_s=0.1, clock="local_timestamp").to_numpy()
    fr = predictive_frame(b, tick=q["tick"], freq_s=10, latencies_ms=(0, 100, 500))
    fr["day"], fr["tick"] = date, q["tick"]
    out = frame_path(symbol, date)
    out.parent.mkdir(parents=True, exist_ok=True)
    fr.to_parquet(out)
    return len(fr), q["tick"]


def add_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--symbols", nargs="+", default=list(SYMBOLS), help="default: %(default)s")
    ap.add_argument("--dates", nargs="+", default=DATES, metavar="YYYY-MM-DD",
                    help="days to build (default: all 31 in-sample days)")


def run(a: argparse.Namespace) -> None:
    for sym in a.symbols:
        for d in a.dates:
            if frame_path(sym, d).exists():
                continue
            t = time.time()
            n, tick = build_frame(sym, d)
            print(f"{sym} {d} rows={n} tick={tick} {time.time() - t:.0f}s", flush=True)
