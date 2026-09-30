# OFI replication — project rules

Replication of Cont–Kukanov–Stoikov (2014) order-flow imbalance on Binance USDT-M perps, plus a predictive-OFI-net-of-costs test. Design: HYPOTHESES.md. Decisions: DECISIONS.md. Status: PROGRESS.md.

## Rules
- HYPOTHESES.md is frozen. Never edit it after the freeze commit.
- Test split dates are never loaded before Phase 4's final run.
- Every analysis run appends a row to research/trial_ledger.csv.
- Never commit raw vendor data. Commit download scripts, not data.
