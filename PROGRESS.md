# Progress

## Phase order
- [x] **Phase 1 (MVP):** BTCUSDT only, 3 days (2023-09-01, 2024-09-01, 2025-09-01). Download, validate, compute OFI, H1 table, one placebo, end to end.
- [ ] **Phase 2:** all BTC days, H1–H4.
- [ ] **Phase 3:** ETH + selected third symbol.
- [ ] **Phase 4:** H5/H6 (only after H1–H4 are written up).
- [ ] **Phase 5:** memo + README.

## Log
- 2026-09-30 — Research design v1 frozen (HYPOTHESES.md). Data source verified: Tardis `quotes` is L2-derived and ~25 ms batched; main dataset `book_ticker`, `quotes` as robustness (see DECISIONS.md).
- 2026-09-30 — Phase 1 done. 35 tests pass. H1 on BTCUSDT book_ticker, 3 days: beta > 0 in 144/144 windows (pass); median R^2 0.73 (IQR 0.61–0.80), above the predicted 0.2–0.6; placebo ±5 R^2 ≈ 0.003. quotes robustness (2025-09-01): R^2 0.79 vs 0.80. Open issues for Phase 2: peak memory 9.2 GB on the 37M-row day (8 GB machine, swapped); book_ticker shows wide transient spreads (p99 11–19 ticks vs 1 tick in quotes); R^2 rising 0.57→0.73→0.80 across years. See reports/phase1_h1.md.
