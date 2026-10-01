# Order-flow imbalance in crypto perps: explains, doesn't predict

A pre-registered replication of Cont, Kukanov & Stoikov (2014) on Binance USDⓈ-M perpetuals (BTCUSDT, ETHUSDT, WLDUSDT; 31 days each, 2023-09 → 2026-03, native top-of-book data). Order-flow imbalance (OFI) over 10-second buckets explains a median **69–73%** of mid-price variance, and its slope scales like 1/depth. But on six held-out test days, using only information already received plus 100 ms of latency, its out-of-sample R² for the **next** 10 seconds is **≤ 0** on every symbol. A sign strategy would need costs of 0.07–0.14 bps per trade to break even, against a 5 bps taker fee.

![Explain vs predict](research/figures/fig4_explain_vs_predict.png)

**→ Full write-up: [research/memo.md](research/memo.md)**

| | BTCUSDT | ETHUSDT | WLDUSDT |
|---|---|---|---|
| H1 OFI explains same-interval ΔMid (β > 0 in all windows; median R²) | ✓ 0.71 | ✓ 0.69 | ✓ 0.73 |
| H2 linear (ΔR² from curvature < 0.02) | ✓ | ✓ | ✗ 0.045 |
| H3 β ∝ 1/depth^λ, λ̂ ∈ [0.7, 1.3] with a tight CI | ✗ CI too wide | ✓ 1.13 | ✓ 1.08 |
| H4 OFI beats trade imbalance | ✓ +0.32 | ✓ +0.34 | ✓ +0.39 |
| **H5** predicts next interval out of sample (test days) | **✗** −0.0008 | **✗** −0.006 | **✗** −0.069 |
| **H6** survives costs (break-even per side vs 5 bps fee) | ✗ 0.11 bps | ✗ 0.07 bps | ✗ 0.14 bps |

## Reproduce

Python 3.14 and 8 GB RAM. Free Tardis.dev first-of-month files: about 6 GB for the BTC example below, 17 GB for the full study.

```bash
python3.14 -m venv .venv && .venv/bin/pip install -e ".[dev,figures]"   # pinned deps
.venv/bin/pytest                                                       # 86 tests, ~3 s, no network
cd scripts && ../.venv/bin/python build_buckets.py --symbol BTCUSDT && ../.venv/bin/python run_phase2.py --symbol BTCUSDT
```

The last line downloads 31 BTC days and reproduces `reports/phase2_BTCUSDT.md`. Full pipeline, in order (all scripts live in `scripts/`):

| Step | Script | Output |
|---|---|---|
| 1. Buckets per symbol (exchange clock) | `build_buckets.py --symbol S` | `data/buckets/…` |
| 2. H1–H4 | `run_phase2.py --symbol S --phase {2,3}` | `reports/phase{2,3}_S.md` |
| 3. Third-symbol selection (2023-08-01 only) | `select_third_symbol.py` | `reports/third_symbol_selection.md` |
| 4. Receive-clock frames | `build_predict_frames.py` | `data/predict/…` |
| 5. H5/H6 train/validation/walk-forward | `run_phase4.py` | `reports/phase4_S.md`, `research/phase4_models.json` |
| 6. One-shot test (already used; refuses to re-run) | `final_test_run.py --final` | `reports/phase4_test.md` |
| 7. Figures | `make_figures.py` | `research/figures/` |

## How this was kept honest

- **Pre-registration:** [HYPOTHESES.md](HYPOTHESES.md) was frozen before the first result. Every interpretation, deviation and bug that touched the analysis is dated in [DECISIONS.md](DECISIONS.md), written *before* the run it governs.
- **Held-out test days:** the data loader refuses to read them except inside the final script, which ran once with frozen coefficients.
- **Trial ledger:** every analysis run is logged in [research/trial_ledger.csv](research/trial_ledger.csv), so the multiple-testing count is visible.
- **Tests on the fragile parts:** hand-computed e_n cases, bucket boundaries, a no-look-ahead property test for the prediction target, chunked-vs-single-pass equality, and a truncated-download check.
- **Raw vendor data is never committed.** Download scripts are.

## Layout

```
src/ofi/     library: OFI (ofi.py), regressions (regress.py), inference (stats.py), prediction (predict.py), I/O, quality
scripts/     pipeline steps (table above)
tests/       pytest suite
reports/     generated results and per-day data-quality reports
research/    memo, figures, trial ledger, frozen Phase 4 models
```

Data: [Tardis.dev](https://docs.tardis.dev/downloadable-csv-files) free first-of-month `book_ticker` and `trades` files for Binance USDⓈ-M futures.
