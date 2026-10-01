# Order-flow imbalance and short-horizon price changes in crypto perpetuals

*Draft, sections on H1–H4 only. H5/H6 (prediction net of costs) are pending and are not reported here. 2026-10-01.*

## Abstract

Does the Cont–Kukanov–Stoikov (2014) result, that short-horizon mid-price changes are linear in order-flow imbalance (OFI) with a slope inversely proportional to depth, hold on Binance USDⓈ-M perpetuals? Using native top-of-book (`bookTicker`) data for BTCUSDT, ETHUSDT and WLDUSDT on 31 days (the 1st of each month, 2023-09 to 2026-03; 1,488 thirty-minute windows per symbol), OFI over 10-second buckets explains a median 69–73% of mid-price variance, and the slope is positive in all 4,464 windows. OFI beats trade imbalance by 0.32–0.39 in median R², with day-block bootstrap CIs that exclude zero for every symbol. The slope scales like 1/depth^λ with λ̂ = 1.13 [0.95, 1.29] (ETH) and 1.08 [0.87, 1.34] (WLD), consistent with λ = 1, while BTC's estimate (0.74 [0.35, 1.06]) is too imprecise to pass the pre-registered test. Biggest caveat: this relation is contemporaneous and partly mechanical, so it explains price moves but does not predict them. Whether it predicts after costs is the question of the next section (H5/H6).

## 1. Question and mechanism

CKS define, for each change to the best quotes, an order-flow contribution

e_n = 1{Pᵇₙ ≥ Pᵇₙ₋₁}·qᵇₙ − 1{Pᵇₙ ≤ Pᵇₙ₋₁}·qᵇₙ₋₁ − 1{Pᵃₙ ≤ Pᵃₙ₋₁}·qᵃₙ + 1{Pᵃₙ ≥ Pᵃₙ₋₁}·qᵃₙ₋₁

and OFI_k = Σ e_n over bucket k. Limit orders added at the bid, and cancellations or market sells hitting the ask, push OFI up; the mirror events push it down. Their model is ΔMid_k = α + β·OFI_k + ε, with β ≈ c/depth: a thick book absorbs the same flow with a smaller price move. On US equities they report an average R² of about 65%.

The mechanism matters for interpretation. If the spread is one tick, the mid can only move when a whole best queue is depleted, and that depletion is exactly the −q_{n−1} term in e_n. In a tick-constrained book, OFI therefore nearly *contains* the price change. High contemporaneous R² is expected and is not, by itself, evidence of a tradable signal.

**Why crypto perps are a useful test:** continuous 24/7 trading, a single dominant venue, no NBBO fragmentation, free tick-level data, and a range of tick constraints across coins (BTC and ETH almost always trade at a 1-tick spread; WLD often does not).

## 2. Data

- **Source:** Tardis.dev free files (1st of each month), Binance USDⓈ-M futures. Main dataset `book_ticker` (native bookTicker, every top-of-book change, 1.2M–61M rows per symbol-day). Tardis `quotes` was rejected as the main source because it is rebuilt from the ~25 ms batched depth stream and folds ~19 events into each row (DECISIONS.md). On one BTC day it gives nearly the same R² (0.79 vs 0.80). `trades` provides the trade-imbalance baseline.
- **Sample:** 31 days per symbol, 2023-09-01 to 2026-03-01. Days from 2026-04 onward are a held-out test set for H5/H6 and are blocked by the data loader.
- **Third symbol:** chosen by a pre-registered rule applied only to 2023-08-01 (pre-sample). Among the top-20 USDT perps by volume, pick the one with the largest share of time at spread > 1 tick, subject to ≥ 1 update/s. The rule selected **WLDUSDT** (3.1%).
- **Cleaning:** none removed except ±2 min around funding times (00/08/16 UTC). Quality checks per day: no missing values, no timestamps going backwards, no crossed books, median receive delay 2.6–11.7 ms. Known defects, kept: rare real orders off the tick grid (≤ 0.007% of rows, with matching trades), and transient wide spreads lasting milliseconds.

## 3. Method and baselines

- **Clock:** exchange timestamp (the relation is mechanical, as of the event).
- **Buckets and windows:** 10 s buckets, 30 min windows, one OLS regression per window with Newey–West standard errors (4 lags). Robustness: 1 s / 30 min and 60 s / 2 h.
- **Depth:** D_w = mean over the window of (best bid size + best ask size)/2, sampled at bucket ends.
- **Baseline (H4):** trade imbalance, TI_k = Σ signed taker volume per bucket.
- **H3:** β_w = exp(a + γ·Z_w)·D_w^(−λ), fitted by nonlinear least squares on β levels, so windows with β ≤ 0 are not dropped. Z = 4-hour UTC block and weekend dummies.
- **Inference:** day-block bootstrap (10,000 draws, seed 20260930) for all aggregate claims, since days are the independent unit and windows within a day are correlated.
- **Guards:** placebo with OFI shifted ±5 buckets; hypotheses and test statistics committed before the corresponding runs (HYPOTHESES.md, DECISIONS.md); every run logged in `research/trial_ledger.csv`.

## 4. Results

![ΔMid vs OFI in the BTC window with median R²](figures/fig1_example_window.png)

*Figure 1. One 30-minute BTC window, chosen as the one closest to the median R² (not hand-picked).*

| Main spec (10 s / 30 min) | BTCUSDT | ETHUSDT | WLDUSDT |
|---|---|---|---|
| **H1** β > 0 (pass: ≥ 95% of windows) | 1488/1488 | 1488/1488 | 1488/1488 |
| H1 median R² [95% CI] | 0.71 [0.68, 0.73] | 0.69 [0.66, 0.70] | 0.73 [0.64, 0.79] |
| **H2** ΔR² from OFI·\|OFI\| (pass: < 0.02) | 0.012 [0.008, 0.017] | 0.011 [0.009, 0.018] | 0.045 [0.022, 0.071] |
| **H3** λ̂ (pass: in [0.7, 1.3], CI width < 0.6) | 0.74 [0.35, 1.06] | 1.13 [0.95, 1.29] | 1.08 [0.87, 1.34] |
| **H4** R²(OFI) − R²(TI) (pass: CI > 0) | 0.32 [0.27, 0.36] | 0.34 [0.29, 0.38] | 0.39 [0.28, 0.47] |
| Placebo (±5 buckets) median R² | 0.002 / 0.003 | 0.003 / 0.003 | 0.003 / 0.003 |
| **Verdicts** | H1 ✓ H2 ✓ **H3 ✗** H4 ✓ | all ✓ | H1 ✓ **H2 ✗** H3 ✓ H4 ✓ |

- **H1:** replicates on every symbol. Median R² of 0.69–0.73 lands above our pre-registered prediction of 0.2–0.6 and above CKS's ~0.65, consistent with these books being more tick-constrained than CKS's stocks (Section 6).
- **H4:** OFI roughly doubles the explanatory power of trade imbalance (Figure 2). Order-book events that are not trades (new limit orders, cancellations) carry most of the information, which is CKS's central point.
- **H3:** ETH and WLD are consistent with λ = 1 (Figure 3). BTC fails on precision, not on its point estimate: its depth varies only about 4× across windows (5th–95th percentile 3.2–13 BTC), which is too little range to pin down a slope. All bootstrap fits converged, and a log-log fit gives a similar 0.81.
- **H2:** linear to within 0.02 of R² for BTC and ETH. WLD shows real curvature (+0.045). Caveat: this test has limited power, because OFI·|OFI| is highly correlated with OFI (≈ 0.92 for Gaussian OFI).

![Per-day median R²: OFI vs trade imbalance](figures/fig2_r2_over_time.png)

*Figure 2. Per-day median window R², OFI (solid) vs trade imbalance (dashed).*

![Window β vs depth, log–log](figures/fig3_beta_vs_depth.png)

*Figure 3. Window β against mean depth, with the NLS fit (solid) and a slope −1 reference (dashed). λ̂ and bootstrap CIs are shown in each panel title.*

## 5. Robustness and what failed

- **Bucket size:** the 1 s / 30 min and 60 s / 2 h specs give the same verdicts for every symbol. R² is lower at both extremes (e.g. BTC 0.62 at 1 s, 0.64 at 60 s, vs 0.71 at 10 s).
- **Time variation:** R² is not stable. BTC rises from 0.57 (2023-09) to ~0.80 (mid-2025), then falls to 0.47 (2026-03). ETH shows a similar late decline. The Phase 1 pilot (3 days) suggested a steady rise, which the full sample contradicts: a reminder of how misleading 3 days can be.
- **Failures, as pre-registered:** H3 on BTC (CI width 0.71 > 0.6) and H2 on WLD (0.045 > 0.02).
- **Multiple testing:** 4 hypotheses × 3 symbols × 3 specs. The H1/H4 conclusions sit far from their thresholds. The closest calls are H2 on BTC and ETH (upper CI ≈ 0.017–0.018 vs 0.02).
- **Bugs found and fixed during the work** (all with regression tests): a pre-midnight seeding bug in bucketing; a silently truncated download; tick inference fooled by very low prices (it briefly mis-measured one candidate in the third-symbol selection, and re-running with the fix gave the same pick); memory blow-up on 50M-row days (fixed with chunked processing, verified identical to single-pass).

## 6. Exploratory: why is R² so high? (not pre-registered)

The tick-constraint mechanism in Section 1 predicts that R² should fall when spreads are wider than one tick. BTC and ETH can't test this (their spread is > 1 tick < 2% of the time). WLD can:

| WLD windows by share of time spread > 1 tick | ~0% | 0.6% | 1.1% | 6.7% | 32% |
|---|---|---|---|---|---|
| Median R² | 0.84 | 0.81 | 0.78 | 0.61 | 0.51 |

Across WLD's 31 days, median R² also tracks the tick's size relative to price (Spearman ρ = 0.75). At WLD's ~$8 peak in March–April 2024 the $0.0001 tick was 0.12 bps of price and R² was 0.47. At ~$0.40 in 2026 it was 2.5 bps and R² was 0.83. This supports the mechanism, but it is exploratory, it involves one coin, and it is confounded with time, activity and depth. It is a hypothesis for a follow-up test, not a finding.

## 7. Limitations

- Only one day per month, so intra-month dynamics and consecutive-day dependence are unobserved.
- A single venue: Binance perps only, with no cross-venue flow.
- The relation is contemporaneous. Nothing above implies predictability or profit; that is what H5/H6 test, on the held-out days, with costs.
- Exchange timestamps have millisecond resolution, so ~70% of bookTicker rows share a millisecond with the previous row. Their order within a millisecond follows the file order.
