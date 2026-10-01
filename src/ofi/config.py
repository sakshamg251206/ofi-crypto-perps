"""Project paths and the frozen sample design (docs/HYPOTHESES.md), in one place.

Paths can be overridden with environment variables (see .env.example):
  OFI_PROJECT_DIR  repository root (reports/, research/ live here); default: the checkout this file is in
  OFI_DATA_DIR     raw downloads and intermediate parquet files; default: <project>/data
"""
import datetime as dt
import os
from pathlib import Path


def _project_dir() -> Path:
    if env := os.environ.get("OFI_PROJECT_DIR"):
        return Path(env).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[2]
    return checkout if (checkout / "pyproject.toml").exists() else Path.cwd()


ROOT = _project_dir()
DATA_DIR = Path(os.environ.get("OFI_DATA_DIR") or ROOT / "data").expanduser()
REPORTS_DIR = ROOT / "reports"
RESEARCH_DIR = ROOT / "research"
FIGURES_DIR = RESEARCH_DIR / "figures"
LEDGER_PATH = RESEARCH_DIR / "trial_ledger.csv"
MODELS_PATH = RESEARCH_DIR / "phase4_models.json"
FINAL_TEST_REPORT = REPORTS_DIR / "phase4_test.md"

DATASET = "book_ticker"  # main dataset (docs/DECISIONS.md, 2026-09-30)
SYMBOLS = ("BTCUSDT", "ETHUSDT", "WLDUSDT")  # WLDUSDT chosen by the pre-registered rule


def first_of_month(start: dt.date, end: dt.date) -> list[str]:
    """ISO dates of every 1st of the month in [start, end]."""
    out, d = [], start.replace(day=1)
    while d <= end:
        if d >= start:
            out.append(d.isoformat())
        d = dt.date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return out


# In-sample days (train + validation); the loader refuses anything in the test split.
DATES = first_of_month(dt.date(2023, 9, 1), dt.date(2026, 3, 1))
TRAIN = [d for d in DATES if d <= "2025-08-01"]
VALID = [d for d in DATES if "2025-09-01" <= d <= "2026-03-01"]
TEST_START, TEST_END = dt.date(2026, 4, 1), dt.date(2026, 9, 30)
TEST = first_of_month(TEST_START, TEST_END)
