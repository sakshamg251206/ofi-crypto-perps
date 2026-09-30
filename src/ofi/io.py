"""Download and load Tardis top-of-book files, with a hard guard on test-split dates."""
import datetime as dt
import shutil
import urllib.request
from pathlib import Path

import pandas as pd

TARDIS_URL = "https://datasets.tardis.dev/v1/binance-futures/{dataset}/{y}/{m}/{d}/{symbol}.csv.gz"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
# HYPOTHESES.md: test split 2026-04 .. 2026-09, untouched until Phase 4's final run.
TEST_START, TEST_END = dt.date(2026, 4, 1), dt.date(2026, 9, 30)

TOB_DTYPES = {"timestamp": "int64", "local_timestamp": "int64", "bid_price": "float64",
              "bid_amount": "float64", "ask_price": "float64", "ask_amount": "float64"}


class HeldOutDateError(RuntimeError):
    """Raised when code tries to touch a test-split date before Phase 4's final run."""


def assert_not_test_date(date: str) -> None:
    if TEST_START <= dt.date.fromisoformat(date) <= TEST_END:
        raise HeldOutDateError(f"{date} is in the held-out test split; not loadable before Phase 4.")


def raw_path(dataset: str, symbol: str, date: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "raw" / dataset / symbol / f"{date}.csv.gz"


def download_day(dataset: str, symbol: str, date: str, data_dir: Path = DATA_DIR) -> Path:
    """Fetch one free first-of-month Tardis file; skip if already on disk."""
    assert_not_test_date(date)
    dest = raw_path(dataset, symbol, date, data_dir)
    if dest.exists():
        return dest
    y, m, d = date.split("-")
    url = TARDIS_URL.format(dataset=dataset, y=y, m=m, d=d, symbol=symbol)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as out:
        shutil.copyfileobj(r, out)
    tmp.rename(dest)  # atomic: a crash never leaves a truncated file under the real name
    return dest


def load_top_of_book(dataset: str, symbol: str, date: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load a quotes/book_ticker file in original row order (sequence within a ms is preserved)."""
    assert_not_test_date(date)
    return pd.read_csv(raw_path(dataset, symbol, date, data_dir),
                       usecols=list(TOB_DTYPES), dtype=TOB_DTYPES)
