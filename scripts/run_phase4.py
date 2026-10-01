"""Phase 4 (H5/H6) on non-test days: fit on train, evaluate on validation, walk-forward robustness.

Run: .venv/bin/python scripts/run_phase4.py [--boot N]
Output: reports/phase4_<SYMBOL>.md, research/phase4_models.json (frozen train fits for the final test run).
Verdicts are NOT issued here: H5/H6 are judged on the test days only (scripts/final_test_run.py).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from build_buckets import DATES
from build_predict_frames import SYMBOLS, frame_path
from ofi.ledger import log_run
from ofi.predict import fit_ols, oos_r2, sign_strategy_pnl
from ofi.stats import block_bootstrap, percentile_ci

ROOT = Path(__file__).resolve().parents[1]
TRAIN = [d for d in DATES if d <= "2025-08-01"]
VALID = [d for d in DATES if "2025-09-01" <= d <= "2026-03-01"]
LATENCIES = (0, 100, 500)
MAIN_L = 100
FEE_BPS = 5.0  # Binance USDⓈ-M VIP 0 taker; secondary sources checked 2026-10-01 (DECISIONS.md)
WALK_MIN_DAYS = 12


def features(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Regressors known at t_k. 'ofi' is the H5 model; the rest are secondary or baselines."""
    return {"ofi": df["x"].to_numpy(), "ofi_over_depth": (df["x"] / df["depth_t"]).to_numpy(),
            "ar1": df["ar_lag"].to_numpy(), "ti": df["ti_lag"].to_numpy()}


def load(symbol: str, dates: list[str]) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(frame_path(symbol, d)) for d in dates])


def fit_all(train: pd.DataFrame) -> dict:
    X = features(train)
    return {f"{m}_L{L}": fit_ols(X[m], train[f"y_{L}"].to_numpy()) for m in X for L in LATENCIES}


def evaluate(df: pd.DataFrame, models: dict, n_boot: int, seed: int = 20260930) -> pd.DataFrame:
    """Out-of-sample R² (with day-block CI for the main row) and sign-strategy economics per model and latency."""
    X = features(df)
    rows = []
    for key, (a, b) in models.items():
        m, L = key.rsplit("_L", 1)
        L = int(L)
        y = df[f"y_{L}"].to_numpy()
        yhat = a + b * X[m]
        r = {"model": m, "L_ms": L, "oos_r2": oos_r2(y, yhat)}
        if m == "ofi" and L == MAIN_L:
            d = df.assign(_yhat=yhat, _y=y)
            draws = block_bootstrap(d, "day", lambda s: oos_r2(s["_y"].to_numpy(), s["_yhat"].to_numpy()),
                                    n=n_boot, seed=seed)
            r["oos_r2_ci"] = percentile_ci(draws)
        strat = pd.DataFrame({"y": y, "yhat": yhat, "mid_entry": df[f"mid_entry_{L}"].to_numpy(),
                              "half_spread_bps": df[f"half_spread_bps_{L}"].to_numpy()}, index=df.index)
        assert df["tick"].nunique() == 1, "tick changed within sample; handle per day"
        tick = df["tick"].iloc[0]
        pnl = sign_strategy_pnl(strat, tick=tick, fee_bps=FEE_BPS, freq_s=10)
        r |= {"gross_bps_per_bucket": pnl["gross_bps_per_bucket"], "break_even_bps": pnl["break_even_bps"],
              "net_bps_per_day": pnl["net_bps"] / df["day"].nunique(),
              "turnover_per_day": pnl["turnover"] / df["day"].nunique(),
              "median_half_spread_bps": float(np.median(df[f"half_spread_bps_{L}"]))}
        rows.append(r)
    return pd.DataFrame(rows)


def walk_forward(symbol: str) -> pd.DataFrame:
    """Expanding window over non-test days: fit on all earlier days, predict the next day (main model)."""
    rows = []
    for i in range(WALK_MIN_DAYS, len(DATES)):
        train, test = load(symbol, DATES[:i]), load(symbol, [DATES[i]])
        a, b = fit_ols(train["x"].to_numpy(), train[f"y_{MAIN_L}"].to_numpy())
        y = test[f"y_{MAIN_L}"].to_numpy()
        yhat = a + b * test["x"].to_numpy()
        rows.append({"day": DATES[i], "b": b, "sse": float(np.sum((y - yhat) ** 2)), "sst0": float(np.sum(y ** 2)),
                     "oos_r2": oos_r2(y, yhat)})
    return pd.DataFrame(rows)


def fmt(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    f = lambda v: (f"[{v[0]:.4f}, {v[1]:.4f}]" if isinstance(v, tuple) else f"{v:.4f}" if isinstance(v, float) else str(v))
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=10_000)
    n_boot = ap.parse_args().boot
    frozen = {}
    for sym in SYMBOLS:
        train, valid = load(sym, TRAIN), load(sym, VALID)
        models = fit_all(train)
        frozen[sym] = {k: list(v) for k, v in models.items()}
        ins = evaluate(train, models, n_boot=200)[["model", "L_ms", "oos_r2"]].rename(columns={"oos_r2": "in_sample_r2"})
        val = evaluate(valid, models, n_boot)
        wf = walk_forward(sym)
        wf_pooled = 1 - wf["sse"].sum() / wf["sst0"].sum()
        main = val[(val.model == "ofi") & (val.L_ms == MAIN_L)].iloc[0]
        for metric in ("oos_r2", "break_even_bps", "net_bps_per_day"):
            log_run(phase="4", symbol=sym, dates=f"train {TRAIN[0]}..{TRAIN[-1]}; valid {VALID[0]}..{VALID[-1]}",
                    dataset="book_ticker", bucket="10s", window="n/a", variant=f"H5/H6 validation ofi L={MAIN_L}ms",
                    metric=metric, value=round(float(main[metric]), 6), notes="validation only; no verdict")
        log_run(phase="4", symbol=sym, dates=f"walk-forward {DATES[WALK_MIN_DAYS]}..{DATES[-1]}", dataset="book_ticker",
                bucket="10s", window="n/a", variant=f"H5 walk-forward ofi L={MAIN_L}ms", metric="pooled_oos_r2",
                value=round(float(wf_pooled), 6), notes="robustness; non-test days only")
        md = [f"# Phase 4 — {sym}: H5/H6 on non-test days (no verdicts; the test run decides)", "",
              f"Receive clock. Fit on train ({TRAIN[0]} → {TRAIN[-1]}, {len(TRAIN)} days); evaluated on validation "
              f"({VALID[0]} → {VALID[-1]}, {len(VALID)} days). Main: model `ofi`, L = {MAIN_L} ms. "
              f"Strategy: hold sign(ŷ) for one 10 s bucket; cost per unit turnover = {FEE_BPS} bps taker + half spread.", "",
              "## Validation (out of sample)", "", fmt(val), "",
              "## Train fit (in sample, for reference only)", "", fmt(ins), "",
              f"## Walk-forward (expanding, refit daily, first {WALK_MIN_DAYS} days as initial train; main model)", "",
              f"Pooled out-of-sample R²: **{wf_pooled:.4f}**", "", fmt(wf[["day", "b", "oos_r2"]]), ""]
        (ROOT / "reports" / f"phase4_{sym}.md").write_text("\n".join(md))
        print(f"{sym}: validation main oos R² = {main.oos_r2:.4f} {main.get('oos_r2_ci')}, "
              f"break-even = {main.break_even_bps:.3f} bps, walk-forward pooled R² = {wf_pooled:.4f}", flush=True)
    (ROOT / "research" / "phase4_models.json").write_text(json.dumps(
        {"fit_on": TRAIN, "fee_bps": FEE_BPS, "main": f"ofi_L{MAIN_L}", "models": frozen}, indent=2))


if __name__ == "__main__":
    main()
