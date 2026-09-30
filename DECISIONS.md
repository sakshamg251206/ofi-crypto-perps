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
