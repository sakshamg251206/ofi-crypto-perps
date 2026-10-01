"""Memo figures for H1–H4 from saved per-window results (no re-estimation except the H3 point fit).

Run: .venv/bin/python scripts/make_figures.py
Output: research/figures/fig{1,2,3}_*.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import LogFormatterSciNotation, NullFormatter
import numpy as np
import pandas as pd

from build_buckets import bucket_path
from ofi.ofi import drop_funding, resample_buckets
from ofi.stats import fit_depth_nls
from run_phase2 import controls

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "figures"
# Validated categorical slots 1–3 (dataviz reference palette, all-pairs, light mode).
SYMBOLS = {"BTCUSDT": ("#2a78d6", "o", 2), "ETHUSDT": ("#eb6834", "s", 3), "WLDUSDT": ("#1baf7a", "^", 3)}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10,
    "lines.linewidth": 2, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def windows(symbol: str) -> pd.DataFrame:
    phase = 2 if symbol == "BTCUSDT" else 3
    return pd.read_csv(ROOT / "research" / f"phase{phase}_windows_{symbol}_10s.csv", index_col=0)


def fig1_example_window() -> None:
    """ΔMid vs OFI in the BTC window whose R² is closest to the median (not hand-picked)."""
    W = windows("BTCUSDT")
    w = (W["r2_ofi"] - W["r2_ofi"].median()).abs().idxmin()
    row = W.loc[w]
    b = drop_funding(resample_buckets(pd.read_parquet(bucket_path(row["day"])), 10), 10)
    g = b[(b.index >= w) & (b.index < w + 1800 * 1_000_000)]
    color = SYMBOLS["BTCUSDT"][0]
    fig, ax = plt.subplots(figsize=(4.8, 3.6))
    ax.scatter(g["ofi"], g["dmid_ticks"], s=14, color=color, edgecolor=SURFACE, linewidth=0.6, alpha=0.85)
    x = np.linspace(g["ofi"].min(), g["ofi"].max(), 50)
    beta, alpha = np.polyfit(g["ofi"], g["dmid_ticks"], 1)
    ax.plot(x, alpha + beta * x, color=INK, linewidth=1.5)
    t = pd.to_datetime(w, unit="us", utc=True)
    ax.set_title(f"BTCUSDT, {t:%Y-%m-%d %H:%M} UTC (median-R² window)", loc="left")
    ax.set_xlabel("OFI per 10 s bucket (BTC)")
    ax.set_ylabel("ΔMid per 10 s bucket (ticks)")
    ax.text(0.03, 0.95, f"β = {beta:.2f} ticks/BTC\nR² = {row['r2_ofi']:.2f}, n = {len(g)}", transform=ax.transAxes,
            va="top", color=INK)
    fig.savefig(OUT / "fig1_example_window.png")


def fig2_r2_over_time() -> None:
    """Per-day median R²: OFI (symbol color) vs trade imbalance (gray, dashed), one panel per symbol."""
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), sharey=True)
    for ax, (sym, (color, marker, _)) in zip(axes, SYMBOLS.items()):
        d = windows(sym).groupby("day")[["r2_ofi", "r2_ti"]].median()
        x = pd.to_datetime(d.index)
        ax.plot(x, d["r2_ofi"], color=color, marker=marker, markersize=4, label="OFI")
        ax.plot(x, d["r2_ti"], color=MUTED, linestyle="--", linewidth=1.5, label="Trade imbalance")
        ax.set_title(sym, loc="left")
        ax.text(x[-1], d["r2_ofi"].iloc[-1], " OFI", color=INK, va="center", fontsize=8)
        ax.text(x[-1], d["r2_ti"].iloc[-1], " TI", color=MUTED, va="center", fontsize=8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(axis="x", rotation=45)
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("Median window R² (10 s buckets)")
    axes[0].legend(loc="lower left", frameon=False)
    fig.savefig(OUT / "fig2_r2_over_time.png")


def fig3_beta_vs_depth(lam_ci: dict[str, tuple[float, float]]) -> None:
    """Window β vs mean depth (log–log), NLS fit at baseline controls, and a slope −1 reference."""
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, (sym, (color, marker, _)) in zip(axes, SYMBOLS.items()):
        W = windows(sym)
        fit = fit_depth_nls(W["beta"].to_numpy(), W["depth_mean"].to_numpy(), controls(W))
        ax.scatter(W["depth_mean"], W["beta"], s=6, marker=marker, color=color, alpha=0.45, linewidth=0)
        d = np.geomspace(W["depth_mean"].quantile(0.01), W["depth_mean"].quantile(0.99), 50)
        ax.plot(d, np.exp(fit["a"]) * d ** -fit["lam"], color=INK, linewidth=1.5, label="NLS fit")
        dm = np.exp(np.log(W["depth_mean"]).mean())
        ref = np.exp(fit["a"]) * dm ** -fit["lam"] * (d / dm) ** -1.0
        ax.plot(d, ref, color=MUTED, linestyle="--", linewidth=1.2, label="slope −1 (CKS)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        for axis in (ax.xaxis, ax.yaxis):
            axis.set_major_formatter(LogFormatterSciNotation())
            axis.set_minor_formatter(NullFormatter())
        lo, hi = lam_ci[sym]
        ax.set_title(f"{sym}: λ̂ = {fit['lam']:.2f} [{lo:.2f}, {hi:.2f}]", loc="left")
        ax.set_xlabel(f"Mean depth D_w ({sym.removesuffix('USDT')})")
    axes[0].set_ylabel("Window β (ticks per unit OFI)")
    axes[0].legend(loc="lower left", frameon=False)
    fig.savefig(OUT / "fig3_beta_vs_depth.png")


def fig4_explain_vs_predict() -> dict:
    """Same test days, same receive clock: OFI vs ΔMid of the same interval vs out-of-sample R² for the next one."""
    import json
    from build_predict_frames import frame_path
    from final_test_run import TEST
    from ofi.predict import oos_r2
    frozen = json.loads((ROOT / "research" / "phase4_models.json").read_text())["models"]
    vals = {}
    for sym in SYMBOLS:
        df = pd.concat([pd.read_parquet(frame_path(sym, d)) for d in TEST])
        same = np.corrcoef(df["x"], df["ar_lag"])[0, 1] ** 2
        a, b = frozen[sym]["ofi_L100"]
        nxt = oos_r2(df["y_100"].to_numpy(), a + b * df["x"].to_numpy())
        vals[sym] = (same, nxt)
    fig, ax = plt.subplots(figsize=(6, 3.4))
    x = np.arange(len(vals))
    w = 0.36
    same_c, next_c = "#2a78d6", "#eb6834"
    for i, (sym, (same, nxt)) in enumerate(vals.items()):
        ax.bar(i - w / 2 - 0.01, same, w, color=same_c, label="Same interval (explains)" if i == 0 else None)
        ax.bar(i + w / 2 + 0.01, nxt, w, color=next_c, label="Next interval, out of sample (predicts)" if i == 0 else None)
        ax.text(i - w / 2 - 0.01, same + 0.02, f"{same:.2f}", ha="center", color=INK, fontsize=8)
        ax.text(i + w / 2 + 0.01, max(nxt, 0) + 0.02, f"{nxt:.3f}", ha="center", color=INK, fontsize=8)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(x, list(vals))
    ax.set_ylim(-0.1, 0.8)
    ax.set_ylabel("R² of ΔMid on OFI (10 s)")
    ax.set_title("Held-out test days, receive clock, 100 ms latency", loc="left")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    ax.grid(axis="x", visible=False)
    fig.savefig(OUT / "fig4_explain_vs_predict.png")
    return vals


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # λ CIs come from the committed reports (10,000-draw bootstrap), not recomputed here.
    lam_ci = {"BTCUSDT": (0.346, 1.057), "ETHUSDT": (0.952, 1.291), "WLDUSDT": (0.873, 1.339)}
    fig1_example_window()
    fig2_r2_over_time()
    fig3_beta_vs_depth(lam_ci)
    print("fig4 values (same-interval R², next-interval OOS R²):", fig4_explain_vs_predict())
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
