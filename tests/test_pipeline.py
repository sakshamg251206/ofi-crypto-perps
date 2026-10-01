"""End-to-end: the real `ofi` CLI on synthetic Tardis-format files in a temporary project (no network)."""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

S = 1_000_000
SYMBOL = "TESTUSDT"
DATES = ["2023-09-01", "2023-10-01"]
LEDGER_HEADER = "run_utc,git_sha,phase,symbol,dates,dataset,bucket,window,variant,metric,value,notes\n"


def _day0(date: str) -> int:
    return int(pd.Timestamp(date, tz="UTC").value // 1000)


def write_day(raw, date: str, seed: int, n: int = 40_000) -> None:
    """A random-walk top of book (whole day, first row 1 ms before midnight) and matching trades."""
    rng = np.random.default_rng(seed)
    day0 = _day0(date)
    ts = np.concatenate([[day0 - 1000], day0 + np.sort(rng.integers(0, 86_400 * S, n - 1))])
    bid = 100.0 + 0.1 * np.cumsum(rng.choice([-1, 0, 0, 0, 1], n))
    book = pd.DataFrame({
        "exchange": "binance-futures", "symbol": SYMBOL, "timestamp": ts, "local_timestamp": ts + 3000,
        "ask_amount": rng.uniform(0.1, 9, n).round(3), "ask_price": (bid + 0.1 * rng.choice([1, 1, 1, 2], n)).round(1),
        "bid_price": bid.round(1), "bid_amount": rng.uniform(0.1, 9, n).round(3),
    })
    m = n // 4
    tts = day0 + np.sort(rng.integers(0, 86_400 * S, m))
    trades = pd.DataFrame({
        "exchange": "binance-futures", "symbol": SYMBOL, "timestamp": tts, "local_timestamp": tts + 3000,
        "id": np.arange(m), "side": rng.choice(["buy", "sell"], m), "price": 100.0, "amount": rng.uniform(0.001, 2, m),
    })
    for dataset, df in (("book_ticker", book), ("trades", trades)):
        path = raw / dataset / SYMBOL / f"{date}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("project")
    (root / "research").mkdir()
    (root / "reports").mkdir()
    (root / "research" / "trial_ledger.csv").write_text(LEDGER_HEADER)
    for i, d in enumerate(DATES):
        write_day(root / "data" / "raw", d, seed=i)
    return root


def ofi(project, *args, check=True):
    env = os.environ | {"OFI_PROJECT_DIR": str(project), "OFI_DATA_DIR": str(project / "data")}
    r = subprocess.run([sys.executable, "-m", "ofi.cli", *args], env=env, capture_output=True, text=True, timeout=300)
    if check and r.returncode:
        raise AssertionError(f"ofi {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def test_help_lists_every_pipeline_step(project):
    out = ofi(project, "--help").stdout
    for cmd in ("status", "buckets", "phase2", "frames", "phase4", "final-test", "figures", "site"):
        assert cmd in out


def test_buckets_then_phase2_then_frames(project):
    ofi(project, "buckets", "--symbol", SYMBOL, "--dates", *DATES)
    for d in DATES:
        b = pd.read_parquet(project / "data" / "buckets" / "book_ticker" / SYMBOL / f"{d}_1s.parquet")
        assert len(b) == 86_400
        assert {"ofi", "dmid_ticks", "depth", "spread_ticks", "n_events", "mid", "ti"} <= set(b.columns)
        assert (project / "reports" / "quality" / f"book_ticker_{SYMBOL}_{d}.md").exists()
    assert "exists, skipping" in ofi(project, "buckets", "--symbol", SYMBOL, "--dates", DATES[0]).stdout

    ofi(project, "phase2", "--symbol", SYMBOL, "--boot", "20")
    report = (project / "reports" / f"phase2_{SYMBOL}.md").read_text()
    assert "**Verdicts**" in report and "median depth (TEST)" in report
    assert (project / "research" / f"phase2_windows_{SYMBOL}_10s.csv").exists()
    ledger = pd.read_csv(project / "research" / "trial_ledger.csv")
    assert set(ledger["symbol"]) == {SYMBOL} and len(ledger) == 18  # 3 specs x (5 metrics + 1 exploratory)

    ofi(project, "frames", "--symbols", SYMBOL, "--dates", *DATES)
    fr = pd.read_parquet(project / "data" / "predict" / SYMBOL / f"{DATES[0]}.parquet")
    assert {"x", "y_0", "y_100", "y_500"} <= set(fr.columns)
    assert (fr["tgt_start_0"] >= fr["feat_end"]).all()

    status = ofi(project, "status").stdout
    assert "final test     not run" in status


def test_held_out_dates_are_refused_by_the_cli(project):
    r = ofi(project, "buckets", "--symbol", SYMBOL, "--dates", "2026-05-01", check=False)
    assert r.returncode != 0 and "HeldOutDateError" in r.stderr
    assert not (project / "data" / "raw" / "book_ticker" / SYMBOL / "2026-05-01.csv.gz").exists()


def test_final_test_requires_explicit_flag(project):
    r = ofi(project, "final-test", check=False)
    assert r.returncode != 0 and "Refusing" in r.stderr


def test_phase2_without_buckets_explains_next_step(project):
    r = ofi(project, "phase2", "--symbol", "NOPEUSDT", check=False)
    assert r.returncode != 0 and "ofi buckets --symbol NOPEUSDT" in r.stderr
