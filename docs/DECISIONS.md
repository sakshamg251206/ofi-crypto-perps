# Decisions log

Append-only. One entry per decision: date, decision, reasoning. Deviations from HYPOTHESES.md go here with a reason.

## 2026-09-30 — Data source: what Tardis `quotes` actually is

**Answer: `quotes` is reconstructed from the L2 depth stream, NOT from `bookTicker`.** It is effectively batched.

Doc quotes (verified 2026-09-30):

- https://docs.tardis.dev/downloadable-csv-files/data-types#quotes —
  > "Top of the book (best bid/ask) data reconstructed from exchanges' real-time WebSocket order book L2 data feeds, with best bid/ask recorded every time the top of the book changes. We on purpose choose this solution over native exchanges real-time quotes feeds [...]"
- https://docs.tardis.dev/downloadable-csv-files/data-types#book_ticker —
  > "Top of the book (best bid/ask) data collected directly from exchanges' real-time WebSocket best bid/offer channels (e.g., Binance bookTicker [...]). Unlike quotes which are derived from L2 order book data, book_ticker is sourced from the native exchange-provided WebSocket best bid/offer feed."
- https://docs.tardis.dev/historical-data-details/binance-futures (the `depth` channel `quotes` is built from) —
  > "Recorded with the fastest API cadence available at the time: until 2020-01-07 it was subscribed as depth@100ms (100ms updates), after that as depth@0ms (real-time dynamically adjusted update speed)."

Measured on BTCUSDT 2026-09-01 (both files are free on the 1st of the month):

| dataset | rows | top-of-book changes | gap between updates (exchange ts), p10 / p50 / p90 / p99 | size (gz) |
|---|---|---|---|---|
| `quotes` | 1,893,504 | 1,893,503 | 26 / 26 / 82 / 218 ms | 25 MB |
| `book_ticker` | 36,920,623 | 36,920,621 | 0 / 0 / 2 / 54 ms | 251 MB |

`quotes` never updates faster than ~26 ms, so "depth@0ms" is in practice a ~25 ms batched feed. `book_ticker` shows ~19.5× more top-of-book changes. Exchange timestamps in both are millisecond resolution (µs field, always a multiple of 1000); ~70% of `book_ticker` rows share their ms timestamp with the previous row.

**Test-split disclosure:** 2026-09-01 is a test-split date. It was loaded once, on 2026-09-30, before the freeze, only to count rows and measure update gaps for this data-source check. No OFI, returns, spreads-vs-flow or regressions were computed on it. The raw files were deleted afterwards.

**Caveat (applies if `quotes` is used):** each e_n computed from consecutive `quotes` rows may aggregate several underlying book events (on average ~19 on this day). When the best price does not change within a batch, the net size change is preserved (the CKS terms telescope), so OFI is unbiased in that case. When the best price moves and moves back within one batch, those events are lost. Expect the bias to be small at 10 s buckets and larger at the 1 s robustness bucket.

**Open (to be decided in Phase 1, before any H1 number is final):** `quotes` (batched, 25 MB/day) vs `book_ticker` (native bookTicker, 251 MB/day; ~28 GB for 37 days × 3 symbols). Phase 1 computes OFI from both on one day and compares.

## 2026-09-30 — Research design v1

- **Exchange timestamp for the contemporaneous replication; local receive timestamp + latency buffer for the predictive tests.** The CKS relation is mechanical, as of the event, so event time is the right clock for H1–H4. For H5/H6 the question is what we could act on, so information is timed by when it arrived (local_timestamp) and the target starts 100 ms later. This prevents look-ahead from exchange/receive clock skew.
- **Per-symbol estimation.** Tick sizes, price levels and quantity units (base coin) differ across symbols, so β values are not comparable in a pooled regression. Pooling would mix units and fake a relation.
- **NLS instead of log-log for H3.** log β̂ is undefined for windows with β̂ ≤ 0. Dropping them would select on the outcome and bias λ̂. Fitting β = c·D^(−λ) directly keeps every window.
- **Funding-window exclusion (±2 min around 00:00, 08:00, 16:00 UTC).** Funding settlements cause mechanical position adjustments and quote withdrawals unrelated to normal order flow. These are a known Binance-perp specific distortion that CKS's stocks don't have.
- **Break-even bps instead of pass/fail for H6.** Fees depend on tier and change over time. A break-even cost lets any reader compare the result to their own costs, and it avoids tuning a pass threshold after seeing results.
- **Third-symbol selection rule applied to pre-sample data (2023-08-01).** Choosing the symbol on in-sample data would be peeking. A mechanical rule on a date before the sample starts fixes the choice without looking at any result. The target is a symbol with spread often > 1 tick, i.e. less tick-constrained, closer to CKS's stocks.

## 2026-09-30 — Main dataset: `book_ticker`; `quotes` as robustness

Resolves the open item above. CKS define e_n per top-of-book event. `book_ticker` (native Binance bookTicker) records each change, while `quotes` batches ~19 events per row. The choice was made on fidelity to the method, before any OFI or regression was computed. Cost: up to ~250 MB / 37M rows per day. Handled by processing one day at a time and keeping only the bucketed output.

## 2026-09-30 — Phase 1 implementation choices

- **Depth D_w is sampled on the bucket grid.** HYPOTHESES.md says "mean over window". Implemented as the book state at the end of each 10 s bucket, averaged over the window's buckets. Averaging over events instead would weight busy moments, and events cluster when depth is thin, so it would understate typical depth. This is an interpretation, not a change.
- **Bucket conventions.** Buckets are left-closed [t, t+Δ). ΔMid_k = mid at end of bucket k minus mid at end of bucket k−1. Empty buckets are kept with OFI = 0 and ΔMid = 0 (no information arrived; dropping them would select on activity). The file's pre-midnight row seeds the initial state but its e_n is not counted.
- **Funding exclusion drops whole buckets** that overlap [F−2 min, F+2 min), including the 23:58–24:00 buckets before the next day's 00:00 funding.
- **Newey–West lags** use the plug-in rule floor(4(n/100)^(2/9)), which gives 4 for n ≈ 170. Fixed in advance, not tuned.
- **Placebo shift is matched by time** (t − 5Δ), not by row position, so the funding gaps don't misalign buckets.
- **Windows with < 30 usable buckets are skipped.**

## 2026-09-30 — Phase 2 analysis specification (written before any Phase 2 result)

These fill in details HYPOTHESES.md leaves open. Fixed before running Phase 2.

- **Sample:** BTCUSDT `book_ticker` + `trades`, 31 days (1st of month, 2023-09 → 2026-03). Test-split days excluded by the loader guard.
- **One pass at 1 s.** 10 s and 60 s buckets are aggregated from the 1 s buckets: OFI, TI, ΔMid and event counts sum (ΔMid telescopes exactly), and depth and spread take the last value. This is covered by a test that the aggregated buckets equal direct bucketing. Raw days are read in 5M-row chunks to stay within 8 GB of RAM (tested: chunked output = single-pass output).
- **Trade imbalance (H4):** TI_k = Σ signed trade size in bucket k, positive when Tardis `side` = buy (taker buy), exchange timestamp.
- **H2 statistic:** median over all windows of R²(ΔMid ~ OFI + OFI·|OFI|) minus median R²(ΔMid ~ OFI). Pass if < 0.02.
- **H4 statistic:** median R²(OFI) − median R²(TI) over all windows. 95% CI = percentile interval from 10,000 bootstrap draws that resample whole days (seed 20260930). Pass if the lower bound > 0.
- **H3 model:** β_w = exp(a + γ·Z_w) · D_w^(−λ), fitted by nonlinear least squares on β levels (`scipy.optimize.least_squares`; scipy is already a statsmodels dependency). Z_w = dummies for 4-hour UTC blocks (00–04 is the baseline) + a weekend dummy. The λ CI comes from the same day-block bootstrap (10,000 draws, same seed). Starting values come from log-log OLS on windows with β̂ > 0 (used only to initialise).
- **H1 aggregate uncertainty:** day-block bootstrap CI for pooled median R².
- **Main specification** is 10 s / 30 min. H1–H4 are also reported at 1 s / 30 min and 60 s / 2 h as robustness. The pass/fail verdicts use the main specification only.
- **Exploratory, not pre-registered:** does R² depend on how often the spread is > 1 tick (window share of bucket-end spreads > 1 tick)? Reported with Spearman ρ and a quintile split, and labelled exploratory in the memo and the ledger.
- **Not repeated:** the `quotes` robustness check (done on 2025-09-01 in Phase 1).

## 2026-09-30 — Off-tick-grid prices are kept

On 2023-11-01, 234 `book_ticker` rows had ask prices off the 0.1 grid (e.g. 34417.43), all with tiny sizes (0.001–0.002 BTC), in five clusters between 16:20 and 21:00 UTC. 158 trades executed at off-grid prices the same day (median 0.001 BTC). So these are real book states, not feed errors, and they are kept. The strict "inferred tick == 0.1" check is replaced by a count of off-grid rows, and the build fails only if they exceed 0.01% of a day. ΔMid in ticks can be fractional at those moments, which is harmless for the regressions.

Also corrected: Phase 1's "duplicate rows" (up to 13k/day) were non-adjacent identical rows, i.e. states recurring within the same millisecond (A→B→A), which contribute real e_n. The quality report now counts only rows identical to the previous row. There are 0 of those on the days checked.

## 2026-10-01 — Phase 3: how the third-symbol rule is applied (written before selection)

Operational details of the HYPOTHESES.md rule, fixed before any 2023-08-01 data is looked at:

- **Universe:** Binance USDⓈ-M perpetuals whose symbol ends in `USDT` (no delivery-date suffix) and that have a daily kline for 2023-08-01 on data.binance.vision (`data/futures/um/daily/klines/<SYM>/1d/`). BTCUSDT and ETHUSDT are excluded because they are already in the sample.
- **Volume ranking:** quote-asset volume (USDT) of that 2023-08-01 daily kline. Quote volume is comparable across coins; base volume is not. Top 20 are kept.
- **Spread measure:** Tardis `book_ticker` for 2023-08-01. Share of 1-second grid points (book state at each 1 s bucket end, same convention as the main pipeline) with spread > 1 tick. No funding exclusion for the selection.
- **Activity filter:** median over 1 s buckets of top-of-book updates ≥ 1.
- **Tick size:** inferred per symbol per day as the largest t in {1, 2, 5} × 10^k such that ≥ 99.99% of rows have bid and ask on the t grid. Exchange tick sizes change over time, so tick is inferred per day rather than taken from today's exchangeInfo. ΔMid and spread are then measured in that day's ticks. Any tick change inside the sample gets logged.
- **Pick:** highest spread > 1 tick share among those passing the activity filter; ties go to higher volume.
- 2023-08-01 is outside the sample and outside the test split, so choosing on it involves no peeking.
- If the chosen symbol is missing on any sample day (e.g. delisted), those days are reported as missing and not replaced. The choice is fixed ex ante, which avoids survivorship bias.

## 2026-10-01 — Third-symbol selection re-run after a tick-inference bug

The first selection run picked WLDUSDT, but `infer_tick` had a bug. For very low-priced coins, price / t rounds to 0 for any large t, so every price looked "on grid". 1000PEPEUSDT (~$0.0013) got tick = 50,000, its spread > 1 tick share came out as 0, and it could not compete. Fix: tick candidates must be ≤ the smallest price (regression test added). The rule itself is unchanged and mechanical, so the selection is simply re-run with the fixed code, and whatever it picks stands, even if it is not WLDUSDT. Disclosure: the WLDUSDT outcome of the buggy run was seen before the re-run. BTC (0.1) and ETH (0.01) ticks are unaffected.

Also: `download_day` now retries dropped connections (a connection reset killed one build); HTTP errors such as 404 still propagate.

## 2026-10-01 — H5 timing interpretation (approved; written before any Phase 4 code)

HYPOTHESES.md (frozen) words H5 as "OFI_k predicts ΔMid over [t_k+100ms, t_{k+1}+100ms]". Under this codebase's bucket convention (bucket k = [t_k, t_{k+1})), the literal reading would make the target overlap the OFI interval. That is look-ahead, and it would just re-measure the contemporaneous H1 effect. The only non-leaky reading, used from here on:

- x_k = OFI over [t_{k−1}, t_k), i.e. known at t_k.
- y_k = mid(t_{k+1} + L) − mid(t_k + L), where L is the latency (main L = 100 ms; also 0 and 500 ms).
- All times on the local receive clock (`local_timestamp`). mid(t) = the last book state received at or before t.

A property test must show the target interval never overlaps the OFI interval, for every L. HYPOTHESES.md itself is not edited.

## 2026-10-01 — Final test run, attempt 1 crashed before evaluation

The approved one-shot run (`final_test_run.py --final`) crashed on its first test day because `build_frame` did not download `trades`. On non-test days the files were already on disk from the Phase 2/3 builds, which hid the bug. Before the crash, BTCUSDT 2026-04-01 `book_ticker` was downloaded and bucketed in memory. No frame was saved and no prediction, R², PnL or report was computed or seen (verified: no test-day frames, no `reports/phase4_test.md`, no FINAL ledger rows). The fix adds the missing download. The frozen coefficients (`research/phase4_models.json`) and evaluation code are unchanged. The same approved run is then repeated.

## 2026-10-01 — Repository reorganised (no analysis change)

The pipeline scripts moved from `scripts/` into the installable package (`src/ofi/pipeline/`) behind one `ofi` command, and the design documents moved into `docs/`. No estimator, sample, threshold, seed or frozen coefficient changed, the committed results were not re-run, and the test split stays locked. Older entries refer to the old script names: `build_buckets.py` → `ofi buckets`, `run_phase1.py` → `ofi phase1`, `run_phase2.py` → `ofi phase2`, `select_third_symbol.py` → `ofi select-symbol`, `build_predict_frames.py` → `ofi frames`, `run_phase4.py` → `ofi phase4`, `final_test_run.py` → `ofi final-test`, `make_figures.py` → `ofi figures`. The per-day table in the Phase 3 reports labelled depth as "(BTC)"; the header now names each symbol's own coin (the numbers were always in that coin).
