# Progress

## Phase order
- [x] **Phase 1 (MVP):** BTCUSDT only, 3 days (2023-09-01, 2024-09-01, 2025-09-01). Download, validate, compute OFI, H1 table, one placebo, end to end.
- [x] **Phase 2:** all BTC days, H1–H4.
- [ ] **Phase 3:** ETH + selected third symbol.
- [ ] **Phase 4:** H5/H6 (only after H1–H4 are written up).
- [ ] **Phase 5:** memo + README.

## Log
- 2026-09-30 — Research design v1 frozen (HYPOTHESES.md). Data source verified: Tardis `quotes` is L2-derived and ~25 ms batched; main dataset `book_ticker`, `quotes` as robustness (see DECISIONS.md).
- 2026-09-30 — Phase 1 done. 35 tests pass. H1 on BTCUSDT book_ticker, 3 days: beta > 0 in 144/144 windows (pass); median R^2 0.73 (IQR 0.61–0.80), above the predicted 0.2–0.6; placebo ±5 R^2 ≈ 0.003. quotes robustness (2025-09-01): R^2 0.79 vs 0.80. Open issues for Phase 2: peak memory 9.2 GB on the 37M-row day (8 GB machine, swapped); book_ticker shows wide transient spreads (p99 11–19 ticks vs 1 tick in quotes); R^2 rising 0.57→0.73→0.80 across years. See reports/phase1_h1.md.
- 2026-09-30 — Phase 2 done (reports/phase2.md). 31 BTC days, 1,488 windows, main spec 10 s / 30 min. H1 PASS (β > 0 in 1488/1488; median R² 0.71 [0.68, 0.73], above the predicted 0.2–0.6). H2 PASS (ΔR² 0.012 [0.008, 0.017]; small but nonzero curvature). H3 FAIL on precision (λ̂ 0.74 [0.35, 1.06], width 0.71 > 0.6; all bootstrap fits converged; depth only spans 3–13 BTC). H4 PASS (R²(OFI) − R²(TI) 0.32 [0.27, 0.36]). Placebo R² ≈ 0.002. Exploratory tick-constraint check inconclusive: BTC's bucket-end spread is > 1 tick only ~0–2% of the time, too little variation. R² is not monotone in time: 0.57 (2023-09) → ~0.80 (mid-2025) → 0.47 (2026-03). Infra fixes: chunked processing (9.2 → 3.2 GB peak), truncated-download detection, off-grid prices kept.
