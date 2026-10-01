"""Show the configuration and which inputs / outputs exist, so you know which step to run next.

Run: ofi status
"""
import argparse
import csv

from ofi.config import (
    DATA_DIR,
    DATASET,
    DATES,
    FINAL_TEST_REPORT,
    LEDGER_PATH,
    MODELS_PATH,
    REPORTS_DIR,
    ROOT,
    SYMBOLS,
    TEST_END,
    TEST_START,
)
from ofi.pipeline.buckets import bucket_path
from ofi.pipeline.frames import frame_path


def _size(path) -> str:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f} {unit}" if unit == "B" else f"{total:.1f} {unit}"
        total /= 1024


def add_arguments(ap: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> None:
    n = len(DATES)
    print(f"project   {ROOT}")
    print(f"data      {DATA_DIR}  ({_size(DATA_DIR / 'raw')} raw downloads)")
    print(f"sample    {n} in-sample days {DATES[0]} → {DATES[-1]}; test split {TEST_START} → {TEST_END} (locked)")
    print()
    print(f"{'symbol':<10}{'buckets':>9}{'frames':>9}   report")
    for sym in SYMBOLS:
        nb = sum(bucket_path(d, sym).exists() for d in DATES)
        nf = sum(frame_path(sym, d).exists() for d in DATES)
        reports = sorted(p.name for p in REPORTS_DIR.glob(f"phase[23]_{sym}.md"))
        print(f"{sym:<10}{f'{nb}/{n}':>9}{f'{nf}/{n}':>9}   {', '.join(reports) or '-'}")
    print()
    rows = sum(1 for _ in csv.reader(LEDGER_PATH.open())) - 1 if LEDGER_PATH.exists() else 0
    print(f"trial ledger   {rows} logged runs ({LEDGER_PATH.relative_to(ROOT)})")
    print(f"frozen models  {'yes' if MODELS_PATH.exists() else 'no'} ({MODELS_PATH.relative_to(ROOT)})")
    used = FINAL_TEST_REPORT.exists()
    print(f"final test     {f'USED — {FINAL_TEST_REPORT.relative_to(ROOT)}' if used else 'not run'}")
    if not any(bucket_path(d, s).exists() for s in SYMBOLS for d in DATES):
        print(f"\nNo {DATASET} buckets yet. Next: `ofi buckets --symbol BTCUSDT --dates 2025-09-01` "
              "(one day, a few hundred MB download) or drop --dates for all 31 days.")
