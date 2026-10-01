"""Append-only trial ledger: every analysis run adds a row (research rule, see CONTRIBUTING.md)."""
import csv
import datetime as dt
import subprocess
from pathlib import Path

from ofi.config import LEDGER_PATH as LEDGER


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True, cwd=LEDGER.parent).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit"


def log_run(path: Path = LEDGER, **fields) -> None:
    """Append one row; columns come from the file's header, unknown fields raise KeyError."""
    with open(path, newline="") as f:
        header = next(csv.reader(f))
    unknown = set(fields) - set(header)
    if unknown:
        raise KeyError(f"not ledger columns: {sorted(unknown)}")
    row = {"run_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "git_sha": _git_sha(), **fields}
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=header).writerow(row)
