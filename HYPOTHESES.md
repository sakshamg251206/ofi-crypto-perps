# Pre-registered hypotheses — frozen 2026-09-30
No changes after the first final run. Deviations get logged in DECISIONS.md with a reason.

## Definitions
- e_n and OFI_k: per Cont–Kukanov–Stoikov (2014), from best bid/ask price and size.
- ΔMid in ticks. OFI and depth in base-coin quantity (contracts as Tardis reports them).
- Depth D_w = mean over window w of (best bid size + best ask size)/2.
- Buckets: 10s main. Robustness: 1s (30-min windows) and 60s (2-hour windows). Main windows: 30 min.
- Exclusions: ±2 min around funding times (00:00, 08:00, 16:00 UTC).
- Estimated per symbol. Never pool symbols in one β regression.

## Hypotheses
| # | Hypothesis | Pass criterion |
|---|---|---|
| H1 | OFI explains same-bucket ΔMid | β > 0 in ≥ 95% of windows. Median R² reported; prediction: 0.2–0.6 (not pass/fail) |
| H2 | Linear relation | Adding OFI·\|OFI\| raises median R² by < 0.02 |
| H3 | β ∝ 1/depth | NLS fit β = c·D^(−λ) across windows, with intraday-bucket and weekend controls: λ̂ ∈ [0.7, 1.3] AND 95% CI width < 0.6 |
| H4 | OFI beats trade imbalance | Median R²(OFI) > R²(trade imbalance); block-bootstrap CI over days excludes 0 |
| H5 | OFI_k predicts ΔMid over [t_k+100ms, t_{k+1}+100ms] | Out-of-sample R² > 0 vs zero forecast on test days. Latency sensitivity at 0/100/500ms reported |
| H6 | Prediction survives costs | Report break-even cost in bps for a sign strategy vs. spread + taker fee. Prior: fails |

## Sample
- Symbols: BTCUSDT and ETHUSDT perps, plus a third chosen by this rule, applied ONLY to 2023-08-01 data: from the top-20 USDT-M perps by volume, pick the one with the highest fraction of time with spread > 1 tick, subject to median ≥ 1 top-of-book update/sec.
- Dates: 1st of each month, 2023-09 to 2026-09.
- H5/H6 split: train 2023-09 to 2025-08, validate 2025-09 to 2026-03, test 2026-04 to 2026-09 (untouched until final run). Walk-forward reported as robustness.

## Inference and guards
- Newey–West errors within windows; block bootstrap over days for aggregate claims.
- Placebo: OFI shifted ±5 buckets must collapse R².
- Every variant tried gets logged in research/trial_ledger.csv.
- Known caveat: BTC/ETH are tick-constrained (spread ≈ 1 tick), unlike CKS's stocks. Discussed in the memo.
