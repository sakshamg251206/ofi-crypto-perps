"""Export the committed results (reports/*.md, research/*.csv) as data for the static results explorer.

Run: ofi site
Output: site/data.js (`window.OFI_RESULTS = {...}`), loaded by site/index.html; works offline and from file://.
Reads only committed outputs, so it needs no downloads and never touches the held-out test data.
The output is deterministic: re-running it on unchanged results produces an identical file.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ofi.config import DATES, MODELS_PATH, REPORTS_DIR, RESEARCH_DIR, ROOT, SYMBOLS, TEST, TRAIN, VALID
from ofi.pipeline.phase2 import controls
from ofi.stats import fit_depth_nls

SITE_DIR = ROOT / "site"
PHASE = {"BTCUSDT": 2, "ETHUSDT": 3, "WLDUSDT": 3}  # which phase report holds each symbol's H1–H4
MAIN_SPEC, MAIN_L = "main 10s/30min", 100
_NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"


def md_tables(path: Path) -> dict[str, list[pd.DataFrame]]:
    """Markdown pipe tables in a report, grouped by the nearest preceding heading ('' before any), in order."""
    tables: dict[str, list[pd.DataFrame]] = {}
    heading, block = "", []

    def flush():
        if len(block) >= 2:
            cells = [[c.strip() for c in re.split(r"(?<!\\)\|", row.strip())[1:-1]] for row in block]
            tables.setdefault(heading, []).append(pd.DataFrame(cells[2:], columns=cells[0]))
        block.clear()

    for line in path.read_text().splitlines():
        if line.startswith("|"):
            block.append(line)
            continue
        flush()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
    flush()
    return tables


def first_table(path: Path) -> pd.DataFrame:
    return next(iter(md_tables(path).values()))[0]


def nums(cell: str) -> list[float]:
    return [float(x) for x in re.findall(_NUM, cell)]


def contemporaneous(symbol: str) -> dict:
    """H1–H4 summary for one symbol from its phase 2/3 report (main spec + robustness R²)."""
    t = first_table(REPORTS_DIR / f"phase{PHASE[symbol]}_{symbol}.md").set_index("")
    main = t[MAIN_SPEC]
    windows, days = nums(main["windows (days)"])
    verdicts = dict(re.findall(r"(H\d) (PASS|FAIL)", main["**Verdicts**"]))
    plc = nums(main["Placebo −5 / +5 median R²"])
    return {
        "windows": int(windows), "days": int(days),
        "beta_pos_share": nums(main["H1: β > 0 share (non-positive)"])[0],
        "r2": nums(main["H1: median R² [95% CI]"]),
        "h2": nums(main["H2: ΔR² from OFI·\\|OFI\\| [CI]"]),
        "lam": nums(main["H3: λ̂ [CI] (width)"])[:3],
        "r2_ti": nums(main["H4: median R² TI"])[0],
        "h4": nums(main["H4: R²(OFI) − R²(TI) [CI]"]),
        "placebo": plc,
        "verdicts": verdicts,
        "specs": {spec: nums(t.loc["H1: median R² [95% CI]", spec])[0] for spec in t.columns},
    }


def _model_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({"model": r["model"], "L_ms": int(r["L_ms"]), "oos_r2": float(r["oos_r2"]),
                     "break_even_bps": float(r["break_even_bps"]),
                     "gross_bps_per_bucket": float(r["gross_bps_per_bucket"])})
    return rows


def predictive(symbol: str, test_tables: dict[str, list[pd.DataFrame]]) -> dict:
    """H5/H6 numbers for one symbol: final test (frozen fits), validation and walk-forward."""
    test_key = next(k for k in test_tables if k.startswith(f"{symbol} — H5"))
    test = test_tables[test_key][0]
    main = test[(test["model"] == "ofi") & (test["L_ms"] == str(MAIN_L))].iloc[0]
    val_path = REPORTS_DIR / f"phase4_{symbol}.md"
    val = md_tables(val_path)["Validation (out of sample)"][0]
    val_main = val[(val["model"] == "ofi") & (val["L_ms"] == str(MAIN_L))].iloc[0]
    wf = re.search(rf"Pooled out-of-sample R²: \*\*({_NUM})\*\*", val_path.read_text())
    return {
        "verdict": test_key.rsplit(" ", 1)[-1],
        "oos_r2": [float(main["oos_r2"]), *nums(main["oos_r2_ci"])],
        "break_even_bps": float(main["break_even_bps"]),
        "median_half_spread_bps": float(main["median_half_spread_bps"]),
        "turnover_per_day": float(main["turnover_per_day"]),
        "models": _model_rows(test),
        "validation_oos_r2": [float(val_main["oos_r2"]), *nums(val_main["oos_r2_ci"])],
        "walk_forward_oos_r2": float(wf.group(1)) if wf else None,
    }


def explore(symbol: str) -> dict:
    """Per-day medians, per-window β/depth points with the H3 point fit, and the exploratory quintile split."""
    W = pd.read_csv(RESEARCH_DIR / f"phase{PHASE[symbol]}_windows_{symbol}_10s.csv", index_col=0)
    g = W.groupby("day")
    per_day = pd.DataFrame({"r2_ofi": g["r2_ofi"].median(), "r2_ti": g["r2_ti"].median(),
                            "depth": g["depth_mean"].median(), "gt1": g["frac_spread_gt1"].median(),
                            "windows": g.size()})
    fit = fit_depth_nls(W["beta"].to_numpy(), W["depth_mean"].to_numpy(), controls(W))
    q = pd.qcut(W["frac_spread_gt1"].rank(method="first"), 5, labels=False)
    return {
        "per_day": [{"day": d, **{k: _round(v) for k, v in r.items()}} for d, r in per_day.iterrows()],
        "windows": {"beta": _round(W["beta"]), "depth": _round(W["depth_mean"]), "r2": _round(W["r2_ofi"]),
                    "day": W["day"].tolist()},
        "depth_fit": {"a": _round(fit["a"]), "lam": _round(fit["lam"])},
        "spread_quintiles": {"r2": _round(W.groupby(q)["r2_ofi"].median()),
                             "share": _round(W.groupby(q)["frac_spread_gt1"].median())},
    }


def _round(v, sig: int = 5):
    """Round to `sig` significant digits (keeps data.js small and stable across platforms)."""
    if isinstance(v, pd.Series):
        return [_round(x, sig) for x in v.tolist()]
    if isinstance(v, (np.integer, int)):
        return int(v)
    v = float(v)
    return 0.0 if v == 0 or not np.isfinite(v) else float(f"{v:.{sig}g}")


def selection() -> list[dict]:
    t = first_table(REPORTS_DIR / "third_symbol_selection.md")
    return [{"symbol": r["symbol"], "quote_volume_musd": float(r["quote_volume_musd"]),
             "frac_spread_gt1": float(r["frac_spread_gt1"]), "median_updates_per_s": float(r["median_updates_per_s"]),
             "eligible": r["eligible"] == "True"} for _, r in t.iterrows()]


def build() -> dict:
    test_tables = md_tables(REPORTS_DIR / "phase4_test.md")
    frozen = json.loads(MODELS_PATH.read_text())
    return {
        "symbols": list(SYMBOLS),
        "sample": {"in_sample": DATES, "train": TRAIN, "validation": VALID, "test": TEST},
        "fee_bps": frozen["fee_bps"],
        "contemporaneous": {s: contemporaneous(s) for s in SYMBOLS},
        "predictive": {s: predictive(s, test_tables) for s in SYMBOLS},
        "explore": {s: explore(s) for s in SYMBOLS},
        "third_symbol": selection(),
    }


def add_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--out", type=Path, default=SITE_DIR / "data.js", help="default: site/data.js")


def run(args: argparse.Namespace) -> None:
    data = build()
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("// Generated by `ofi site` from reports/ and research/. Do not edit by hand.\n"
                        f"window.OFI_RESULTS = {body};\n")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
