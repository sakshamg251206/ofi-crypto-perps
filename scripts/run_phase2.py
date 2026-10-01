"""H1–H4 on all non-test days of one symbol, per the Phase 2 spec in DECISIONS.md (2026-09-30).

Run: .venv/bin/python scripts/run_phase2.py [--symbol BTCUSDT] [--phase 2] [--boot N]
Input: data/buckets/book_ticker/<SYMBOL>/<date>_1s.parquet (scripts/build_buckets.py)
Output: reports/phase<P>_<SYMBOL>.md, research/phase<P>_windows_<SYMBOL>_<freq>s.csv, ledger rows.
"""
import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from build_buckets import DATES, bucket_path
from ofi.ledger import log_run
from ofi.ofi import drop_funding, resample_buckets
from ofi.regress import window_features, window_regressions
from ofi.stats import block_bootstrap, fit_depth_nls, percentile_ci

ROOT = Path(__file__).resolve().parents[1]
SPECS = [("main 10s/30min", 10, 1800), ("robust 1s/30min", 1, 1800), ("robust 60s/2h", 60, 7200)]


def windows_for_day(b1: pd.DataFrame, date: str, freq_s: int, window_s: int) -> pd.DataFrame:
    """All per-window regression outputs and features for one day and one spec."""
    b = b1 if freq_s == 1 else resample_buckets(b1, freq_s)
    b = drop_funding(b, freq_s)
    b = b.assign(ofi_abs=b["ofi"] * b["ofi"].abs())
    reg = lambda **kw: window_regressions(b, freq_s=freq_s, window_s=window_s, **kw)
    ofi = reg()
    w = ofi[["beta", "t_nw", "r2", "n"]].rename(columns={"r2": "r2_ofi"})
    w["r2_quad"] = reg(xcols=("ofi", "ofi_abs"))["r2"]
    w["r2_ti"] = reg(xcols=("ti",))["r2"]
    w["r2_plc_p5"] = reg(shift=5)["r2"]
    w["r2_plc_m5"] = reg(shift=-5)["r2"]
    w = w.join(window_features(b, window_s))
    hours = (w.index // 3_600_000_000) % 24
    w["block"] = hours // 4
    w["weekend"] = int(dt.date.fromisoformat(date).weekday() >= 5)
    w["day"] = date
    w["events"] = int(b1["n_events"].sum())
    return w


def controls(W: pd.DataFrame) -> pd.DataFrame:
    """4-hour UTC block dummies (00–04 baseline) + weekend; constant columns dropped (e.g. in a bootstrap draw)."""
    Z = pd.get_dummies(pd.Categorical(W["block"], categories=range(6)), prefix="blk", drop_first=True).astype(float)
    Z["weekend"] = W["weekend"].to_numpy(float)
    return Z.loc[:, Z.std() > 0]


def stats_vector(W: pd.DataFrame) -> np.ndarray:
    """[median R² OFI, H2 diff, H4 diff, λ] for one (re)sample of days."""
    fit = fit_depth_nls(W["beta"].to_numpy(), W["depth_mean"].to_numpy(), controls(W))
    return np.array([W["r2_ofi"].median(), W["r2_quad"].median() - W["r2_ofi"].median(),
                     W["r2_ofi"].median() - W["r2_ti"].median(), fit["lam"]])


def analyse(W: pd.DataFrame, n_boot: int) -> dict:
    point = stats_vector(W)
    draws = block_bootstrap(W, "day", stats_vector, n=n_boot)
    lo, hi = percentile_ci(draws)
    fit = fit_depth_nls(W["beta"].to_numpy(), W["depth_mean"].to_numpy(), controls(W))
    rho, p = spearmanr(W["r2_ofi"], W["frac_spread_gt1"])
    q = pd.qcut(W["frac_spread_gt1"].rank(method="first"), 5, labels=False)
    return {
        "windows": len(W), "days": W["day"].nunique(),
        "frac_beta_pos": (W["beta"] > 0).mean(), "n_beta_nonpos": int((W["beta"] <= 0).sum()),
        "r2_ofi_median": point[0], "r2_ofi_ci": (lo[0], hi[0]),
        "r2_ofi_iqr": (W["r2_ofi"].quantile(0.25), W["r2_ofi"].quantile(0.75)),
        "h2_diff": point[1], "h2_ci": (lo[1], hi[1]),
        "h4_diff": point[2], "h4_ci": (lo[2], hi[2]), "r2_ti_median": W["r2_ti"].median(),
        "lam": point[3], "lam_ci": (lo[3], hi[3]), "nls_converged": fit["converged"], "gamma": fit["gamma"],
        "placebo_r2_median": (W["r2_plc_m5"].median(), W["r2_plc_p5"].median()),
        "expl_spearman": (rho, p),
        "expl_r2_by_spread_quintile": W.groupby(q)["r2_ofi"].median().round(3).tolist(),
        "expl_spread_gt1_by_quintile": W.groupby(q)["frac_spread_gt1"].median().round(3).tolist(),
    }


def verdicts(r: dict) -> dict:
    lam_lo, lam_hi = r["lam_ci"]
    return {
        "H1": "PASS" if r["frac_beta_pos"] >= 0.95 else "FAIL",
        "H2": "PASS" if r["h2_diff"] < 0.02 else "FAIL",
        "H3": "PASS" if 0.7 <= r["lam"] <= 1.3 and lam_hi - lam_lo < 0.6 else "FAIL",
        "H4": "PASS" if r["h4_ci"][0] > 0 else "FAIL",
    }


def fmt_ci(ci) -> str:
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def report(results: dict, per_day: pd.DataFrame, n_boot: int, symbol: str, phase: int, missing: list[str]) -> str:
    lines = [f"# Phase {phase} — H1–H4, {symbol} book_ticker, {len(per_day)} days (2023-09 → 2026-03)", "",
             f"Missing days (reported, not replaced): {missing or 'none'}", "",
             f"Exchange timestamps. Funding ±2 min excluded. Day-block bootstrap, {n_boot:,} draws, seed 20260930.",
             "Verdicts use the main spec only (DECISIONS.md, Phase 2 spec). Robustness specs shown for comparison.", ""]
    lines += ["| | " + " | ".join(results) + " |", "|---|" + "---|" * len(results)]
    rows = [
        ("windows (days)", lambda r: f"{r['windows']} ({r['days']})"),
        ("H1: β > 0 share (non-positive)", lambda r: f"{r['frac_beta_pos']:.3f} ({r['n_beta_nonpos']})"),
        ("H1: median R² [95% CI]", lambda r: f"{r['r2_ofi_median']:.3f} {fmt_ci(r['r2_ofi_ci'])}"),
        ("H1: R² IQR", lambda r: fmt_ci(r["r2_ofi_iqr"])),
        ("H2: ΔR² from OFI·\\|OFI\\| [CI]", lambda r: f"{r['h2_diff']:.4f} {fmt_ci(r['h2_ci'])}"),
        ("H3: λ̂ [CI] (width)", lambda r: f"{r['lam']:.3f} {fmt_ci(r['lam_ci'])} ({r['lam_ci'][1] - r['lam_ci'][0]:.3f})"),
        ("H4: median R² TI", lambda r: f"{r['r2_ti_median']:.3f}"),
        ("H4: R²(OFI) − R²(TI) [CI]", lambda r: f"{r['h4_diff']:.3f} {fmt_ci(r['h4_ci'])}"),
        ("Placebo −5 / +5 median R²", lambda r: f"{r['placebo_r2_median'][0]:.4f} / {r['placebo_r2_median'][1]:.4f}"),
    ]
    for name, f in rows:
        lines.append(f"| {name} | " + " | ".join(f(r) for r in results.values()) + " |")
    lines.append("| **Verdicts** | " + " | ".join(
        ", ".join(f"{h} {v}" for h, v in verdicts(r).items()) for r in results.values()) + " |")

    main = results[SPECS[0][0]]
    lines += ["", "## H3 controls (main spec, point estimates)", "",
              ", ".join(f"{k} = {v:.3f}" for k, v in main["gamma"].items()) + f"; NLS converged: {main['nls_converged']}",
              "", "## Exploratory (not pre-registered): R² vs share of spread > 1 tick", ""]
    for name, r in results.items():
        rho, p = r["expl_spearman"]
        lines.append(f"- **{name}:** Spearman ρ = {rho:.3f} (p = {p:.2g}). Median R² by spread-share quintile (low→high): "
                     f"{r['expl_r2_by_spread_quintile']}; quintile median share: {r['expl_spread_gt1_by_quintile']}")
    lines += ["", "## Per day (main spec)", "",
              "| day | events | windows | β>0 share | median R² | median R² TI | median depth (BTC) | spread>1 share |",
              "|---|---|---|---|---|---|---|---|"]
    for d, r in per_day.iterrows():
        lines.append(f"| {d} | {r.events:,.0f} | {r.windows:.0f} | {r.beta_pos:.3f} | {r.r2:.3f} | {r.r2_ti:.3f} | "
                     f"{r.depth:.2f} | {r.gt1:.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=10_000)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--phase", type=int, default=2)
    args = ap.parse_args()
    n_boot, symbol, phase = args.boot, args.symbol, args.phase

    missing = [d for d in DATES if not bucket_path(d, symbol).exists()]
    days = {d: pd.read_parquet(bucket_path(d, symbol)) for d in DATES if d not in missing}
    results, per_day = {}, None
    for name, freq_s, window_s in SPECS:
        W = pd.concat([windows_for_day(b1, d, freq_s, window_s) for d, b1 in days.items()]).dropna()
        W.to_csv(ROOT / "research" / f"phase{phase}_windows_{symbol}_{freq_s}s.csv")
        print(f"[{name}] {len(W)} windows, bootstrapping", flush=True)
        results[name] = analyse(W, n_boot)
        v = verdicts(results[name])
        for metric in ("frac_beta_pos", "r2_ofi_median", "h2_diff", "lam", "h4_diff"):
            log_run(phase=str(phase), symbol=symbol, dates=f"{DATES[0]}..{DATES[-1]} ({len(days)}d)", dataset="book_ticker",
                    bucket=f"{freq_s}s", window=f"{window_s // 60}min", variant=f"H1-H4 {name}", metric=metric,
                    value=round(float(results[name][metric]), 6), notes=" ".join(f"{h}={x}" for h, x in v.items()))
        log_run(phase=str(phase), symbol=symbol, dates=f"{DATES[0]}..{DATES[-1]} ({len(days)}d)", dataset="book_ticker",
                bucket=f"{freq_s}s", window=f"{window_s // 60}min", variant=f"exploratory spread>1 {name}",
                metric="spearman_r2_vs_spread_gt1", value=round(float(results[name]["expl_spearman"][0]), 6),
                notes="exploratory, not pre-registered")
        if per_day is None:
            g = W.groupby("day")
            per_day = pd.DataFrame({"events": g["events"].first(), "windows": g.size(),
                                    "beta_pos": g["beta"].apply(lambda s: (s > 0).mean()), "r2": g["r2_ofi"].median(),
                                    "r2_ti": g["r2_ti"].median(), "depth": g["depth_mean"].median(),
                                    "gt1": g["frac_spread_gt1"].median()})

    md = report(results, per_day, n_boot, symbol, phase, missing)
    (ROOT / "reports" / f"phase{phase}_{symbol}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
