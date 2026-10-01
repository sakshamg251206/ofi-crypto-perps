"""THE one-shot H5/H6 test (HYPOTHESES.md): frozen train-period fits evaluated on the held-out test days.

Run once, only after explicit approval:  .venv/bin/python scripts/final_test_run.py --final
Refuses to run if reports/phase4_test.md exists. Output is committed whatever it shows.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from build_predict_frames import SYMBOLS, build_frame, frame_path
from ofi.io import unlock_test_dates
from ofi.ledger import log_run
from run_phase4 import MAIN_L, evaluate, fmt

ROOT = Path(__file__).resolve().parents[1]
TEST = ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
OUT = ROOT / "reports" / "phase4_test.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="confirm this is the single final test run")
    if not ap.parse_args().final:
        sys.exit("Refusing: pass --final to run the one-shot test (see RULES.md).")
    if OUT.exists():
        sys.exit(f"Refusing: {OUT} exists; the test split has already been used.")
    frozen = json.loads((ROOT / "research" / "phase4_models.json").read_text())

    md = ["# Phase 4 — FINAL TEST (H5/H6), held-out days " + f"{TEST[0]} → {TEST[-1]}", "",
          f"Frozen fits from train days only ({frozen['fit_on'][0]} → {frozen['fit_on'][-1]}). "
          f"Main: `{frozen['main']}`. Cost: {frozen['fee_bps']} bps taker + half spread per unit turnover.", "",
          "H5 PASS if main out-of-sample R² > 0. H6 is reported as break-even bps (prior: fails).", ""]
    with unlock_test_dates():
        for sym in SYMBOLS:
            for d in TEST:
                if not frame_path(sym, d).exists():
                    build_frame(sym, d)
            df = pd.concat([pd.read_parquet(frame_path(sym, d)) for d in TEST])
            models = {k: tuple(v) for k, v in frozen["models"][sym].items()}
            res = evaluate(df, models, n_boot=10_000)
            main = res[(res.model == "ofi") & (res.L_ms == MAIN_L)].iloc[0]
            verdict = "PASS" if main.oos_r2 > 0 else "FAIL"
            for metric in ("oos_r2", "break_even_bps", "net_bps_per_day"):
                log_run(phase="4-FINAL", symbol=sym, dates=f"{TEST[0]}..{TEST[-1]}", dataset="book_ticker", bucket="10s",
                        window="n/a", variant=f"FINAL TEST ofi L={MAIN_L}ms", metric=metric,
                        value=round(float(main[metric]), 6), notes=f"H5={verdict}")
            md += [f"## {sym} — H5 {verdict}", "", fmt(res), ""]
    OUT.write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
