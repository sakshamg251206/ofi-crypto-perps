# Phase 1 — H1 (BTCUSDT, 10 s buckets, 30 min windows, exchange timestamp)

H1 pass criterion: beta > 0 in >= 95% of windows. Median R^2 predicted 0.2-0.6 (not pass/fail).
Placebo: OFI shifted +/-5 buckets; R^2 should collapse.

| dataset | date | windows | frac_beta_pos | n_beta_nonpos | r2_median | r2_q25 | r2_q75 | t_nw_median | placebo-5_r2_median | placebo+5_r2_median |
|---|---|---|---|---|---|---|---|---|---|---|
| book_ticker | 2023-09-01 | 48 | 1.000 | 0 | 0.569 | 0.481 | 0.664 | 11.982 | 0.002 | 0.003 |
| book_ticker | 2024-09-01 | 48 | 1.000 | 0 | 0.725 | 0.654 | 0.780 | 15.570 | 0.004 | 0.003 |
| book_ticker | 2025-09-01 | 48 | 1.000 | 0 | 0.803 | 0.771 | 0.834 | 19.996 | 0.002 | 0.002 |
| quotes | 2025-09-01 | 48 | 1.000 | 0 | 0.788 | 0.724 | 0.807 | 18.425 | 0.003 | 0.002 |
| book_ticker | pooled (3 days) | 144 | 1.000 | 0 | 0.733 | 0.612 | 0.795 | 15.523 | 0.002 | 0.003 |
