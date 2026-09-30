import numpy as np
import pandas as pd
import pytest

from ofi.ofi import bucketize, drop_funding

S = 1_000_000  # microseconds per second
DAY0 = 1_693_526_400 * S  # 2023-09-01 00:00:00 UTC
TICK = 0.1


def book(rows):
    """rows: (seconds after DAY0, bid_px, bid_sz, ask_px, ask_sz)."""
    df = pd.DataFrame(rows, columns=["sec", "bid_price", "bid_amount", "ask_price", "ask_amount"])
    df["timestamp"] = DAY0 + (df.pop("sec") * S).round().astype("int64")
    return df


def test_event_on_boundary_goes_to_later_bucket():
    b = bucketize(book([(0.0, 100.0, 5, 100.1, 3), (10.0, 100.0, 8, 100.1, 3)]), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "ofi"] == 0
    assert b.loc[DAY0 + 10 * S, "ofi"] == pytest.approx(3.0)


def test_ofi_sums_e_within_bucket():
    rows = [(0.0, 100.0, 5, 100.1, 3), (1.0, 100.0, 8, 100.1, 3), (2.0, 100.0, 8, 100.1, 7)]
    b = bucketize(book(rows), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "ofi"] == pytest.approx(3.0 - 4.0)
    assert b.loc[DAY0, "n_events"] == 3


def test_grid_covers_whole_day_and_empty_buckets_are_zero():
    b = bucketize(book([(0.0, 100.0, 5, 100.1, 3), (25.0, 100.0, 8, 100.1, 3)]), freq_s=10, tick=TICK)
    assert len(b) == 8640
    assert b.index[0] == DAY0
    assert b.loc[DAY0 + 10 * S, ["ofi", "dmid_ticks", "n_events"]].tolist() == [0, 0, 0]


def test_dmid_in_ticks_lands_in_bucket_where_mid_moved():
    # mid 100.05 -> 100.15 (bid+ask both up 1 tick) at t=15s -> +1 tick in bucket [10, 20)
    rows = [(-0.002, 100.0, 5, 100.1, 3), (15.0, 100.1, 5, 100.2, 3)]
    b = bucketize(book(rows), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "dmid_ticks"] == 0
    assert b.loc[DAY0 + 10 * S, "dmid_ticks"] == pytest.approx(1.0)
    assert b.loc[DAY0 + 20 * S, "dmid_ticks"] == 0


def test_pre_midnight_row_seeds_state_but_not_ofi():
    # Row 2 ms before midnight is the initial state; its own e_n must not count.
    rows = [(-0.002, 100.0, 5, 100.1, 3), (1.0, 100.0, 8, 100.1, 3)]
    b = bucketize(book(rows), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "ofi"] == pytest.approx(3.0)
    assert b.loc[DAY0, "dmid_ticks"] == 0


def test_depth_is_state_at_bucket_end_forward_filled():
    rows = [(0.0, 100.0, 4, 100.1, 2), (5.0, 100.0, 10, 100.1, 6)]
    b = bucketize(book(rows), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "depth"] == pytest.approx(8.0)          # (10 + 6) / 2
    assert b.loc[DAY0 + 30 * S, "depth"] == pytest.approx(8.0)  # carried forward


def _grid(*hms):
    idx = [DAY0 + (h * 3600 + m * 60 + s) * S for h, m, s in hms]
    return pd.DataFrame({"ofi": np.zeros(len(idx))}, index=pd.Index(idx, name="t"))


def test_drop_funding_removes_buckets_overlapping_two_minutes_around_funding():
    g = _grid((7, 57, 50), (7, 58, 0), (7, 59, 0), (8, 1, 50), (8, 2, 0), (23, 58, 0), (0, 1, 0), (12, 0, 0))
    kept = drop_funding(g, freq_s=10)
    kept_sec = sorted(((kept.index - DAY0) // S).tolist())
    assert kept_sec == sorted([7 * 3600 + 57 * 60 + 50, 8 * 3600 + 2 * 60, 12 * 3600])
