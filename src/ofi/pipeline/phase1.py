"""Phase 1 pilot: BTCUSDT, 3 days, download -> quality -> OFI -> H1 table -> placebo -> ledger.

Run: ofi phase1
Output: reports/phase1_h1.md, reports/quality/phase1/<dataset>_BTCUSDT_<date>.md, ledger rows.
Needs ~10 GB of RAM: it loads whole days in memory (later phases stream in chunks).
"""
import argparse
import gc
import json

import pandas as pd

from ofi.config import DATA_DIR
from ofi.config import REPORTS_DIR as REPORTS
from ofi.io import download_day, load_top_of_book
from ofi.ledger import log_run
from ofi.ofi import bucketize, drop_funding
from ofi.quality import quality_report
from ofi.regress import window_regressions

SYMBOL, TICK, FREQ_S, WINDOW_S = "BTCUSDT", 0.1, 10, 1800
RUNS = [("book_ticker", "2023-09-01"), ("book_ticker", "2024-09-01"), ("book_ticker", "2025-09-01"),
        ("quotes", "2025-09-01")]  # quotes = robustness (DECISIONS.md)


def process_day(dataset: str, date: str) -> pd.DataFrame:
    """Download, quality-check and bucketize one day; returns funding-filtered buckets."""
    download_day(dataset, SYMBOL, date)
    book = load_top_of_book(dataset, SYMBOL, date)
    q = quality_report(book, TICK)
    if q["inferred_tick"] != TICK:
        raise ValueError(f"{dataset} {date}: inferred tick {q['inferred_tick']} != {TICK}")

    buckets = bucketize(book, freq_s=FREQ_S, tick=TICK)
    del book
    gc.collect()
    kept = drop_funding(buckets, freq_s=FREQ_S)
    q |= {"buckets": len(buckets), "buckets_dropped_funding": len(buckets) - len(kept),
          "frac_empty_buckets": float((buckets["n_events"] == 0).mean()),
          "frac_dmid_zero": float((kept["dmid_ticks"] == 0).mean())}

    out = DATA_DIR / "buckets" / dataset / SYMBOL / f"{date}_{FREQ_S}s.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    buckets.to_parquet(out)
    qdir = REPORTS / "quality" / "phase1"
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{dataset}_{SYMBOL}_{date}.md").write_text(
        f"# Data quality — {dataset} {SYMBOL} {date}\n\n```json\n{json.dumps(q, indent=2)}\n```\n")
    return kept


def summarize(reg: pd.DataFrame, placebo: dict[int, pd.DataFrame]) -> dict:
    r2 = reg["r2"]
    return {"windows": len(reg), "frac_beta_pos": (reg["beta"] > 0).mean(),
            "n_beta_nonpos": int((reg["beta"] <= 0).sum()), "r2_median": r2.median(),
            "r2_q25": r2.quantile(0.25), "r2_q75": r2.quantile(0.75), "t_nw_median": reg["t_nw"].median(),
            **{f"placebo{s:+d}_r2_median": p["r2"].median() for s, p in placebo.items()}}


def add_arguments(ap: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> None:
    REPORTS.mkdir(exist_ok=True)
    rows, pooled = [], []
    for dataset, date in RUNS:
        print(f"[{dataset} {date}] processing", flush=True)
        kept = process_day(dataset, date)
        reg = window_regressions(kept, freq_s=FREQ_S, window_s=WINDOW_S)
        placebo = {s: window_regressions(kept, freq_s=FREQ_S, window_s=WINDOW_S, shift=s) for s in (-5, 5)}
        rows.append({"dataset": dataset, "date": date, **summarize(reg, placebo)})
        if dataset == "book_ticker":
            pooled.append((reg, placebo))
        for metric in ("frac_beta_pos", "r2_median", "placebo+5_r2_median", "placebo-5_r2_median"):
            log_run(phase="1", symbol=SYMBOL, dates=date, dataset=dataset, bucket=f"{FREQ_S}s",
                    window=f"{WINDOW_S // 60}min", variant="H1 contemporaneous", metric=metric,
                    value=round(rows[-1][metric], 6))

    reg_all = pd.concat([r for r, _ in pooled])
    plc_all = {s: pd.concat([p[s] for _, p in pooled]) for s in (-5, 5)}
    rows.append({"dataset": "book_ticker", "date": "pooled (3 days)", **summarize(reg_all, plc_all)})
    log_run(phase="1", symbol=SYMBOL, dates="2023-09-01;2024-09-01;2025-09-01", dataset="book_ticker",
            bucket=f"{FREQ_S}s", window=f"{WINDOW_S // 60}min", variant="H1 contemporaneous pooled",
            metric="frac_beta_pos", value=round(rows[-1]["frac_beta_pos"], 6))

    table = pd.DataFrame(rows)
    fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    md = "\n".join(["| " + " | ".join(table.columns) + " |", "|" + "---|" * len(table.columns)]
                   + ["| " + " | ".join(fmt(v) for v in r) + " |" for r in table.itertuples(index=False)])
    (REPORTS / "phase1_h1.md").write_text(
        "# Phase 1 — H1 (BTCUSDT, 10 s buckets, 30 min windows, exchange timestamp)\n\n"
        "H1 pass criterion: beta > 0 in >= 95% of windows. Median R^2 predicted 0.2-0.6 (not pass/fail).\n"
        "Placebo: OFI shifted +/-5 buckets; R^2 should collapse.\n\n" + md + "\n")
    print(md)
