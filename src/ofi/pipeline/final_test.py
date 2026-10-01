"""THE one-shot H5/H6 test (docs/HYPOTHESES.md): frozen train-period fits evaluated on the held-out test days.

Run once, only after explicit approval:  ofi final-test --final
Refuses to run if reports/phase4_test.md exists (it does: the test split has been used). Output is committed
whatever it shows.
"""
import argparse
import json

import pandas as pd

from ofi.config import FINAL_TEST_REPORT as OUT
from ofi.config import MODELS_PATH, SYMBOLS, TEST
from ofi.io import unlock_test_dates
from ofi.ledger import log_run
from ofi.pipeline.frames import build_frame, frame_path
from ofi.pipeline.phase4 import MAIN_L, evaluate, fmt


def add_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--final", action="store_true", help="confirm this is the single final test run")


def run(args: argparse.Namespace) -> None:
    if not args.final:
        raise SystemExit("Refusing: pass --final to run the one-shot test (see CONTRIBUTING.md, research rules).")
    if OUT.exists():
        raise SystemExit(f"Refusing: {OUT} exists; the test split has already been used.")
    frozen = json.loads(MODELS_PATH.read_text())

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
