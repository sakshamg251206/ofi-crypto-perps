"""Per-day H5/H6 frames on the receive clock (DECISIONS.md, 2026-10-01): x = OFI over [t_{k-1}, t_k),
y_L = mid(t_{k+1}+L) - mid(t_k+L), for L in {0, 100, 500} ms. Non-test days only (loader guard).

Run: .venv/bin/python scripts/build_predict_frames.py [--symbols BTCUSDT ETHUSDT WLDUSDT] [--dates ...]
Output: data/predict/<SYMBOL>/<date>.parquet
"""
import argparse
import time

from build_buckets import DATES, day_buckets
from ofi.io import DATA_DIR, load_trades
from ofi.ofi import trade_imbalance
from ofi.predict import predictive_frame

SYMBOLS = ["BTCUSDT", "ETHUSDT", "WLDUSDT"]


def frame_path(symbol: str, date: str):
    return DATA_DIR / "predict" / symbol / f"{date}.parquet"


def build_frame(symbol: str, date: str):
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=SYMBOLS)
    ap.add_argument("--dates", nargs="+", default=DATES)
    a = ap.parse_args()
    for sym in a.symbols:
        for d in a.dates:
            if frame_path(sym, d).exists():
                continue
            t = time.time()
            n, tick = build_frame(sym, d)
            print(f"{sym} {d} rows={n} tick={tick} {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
