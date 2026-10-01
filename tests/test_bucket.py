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


# ---- Phase 2: chunked processing, resampling, spread, trade imbalance ----
from ofi.ofi import bucketize_chunks, resample_buckets, trade_imbalance


def random_book(n=5000, seed=1):
    """Random-walk top of book over the first ~2 hours of DAY0, starting 1 ms before midnight."""
    rng = np.random.default_rng(seed)
    sec = np.concatenate([[-0.001], np.sort(rng.uniform(0, 7200, n - 1))])
    bid = 100.0 + 0.1 * np.cumsum(rng.choice([-1, 0, 0, 0, 1], n))
    spread = 0.1 * rng.choice([1, 1, 1, 2, 3], n)
    rows = list(zip(sec, bid, rng.uniform(0.1, 9, n), bid + spread, rng.uniform(0.1, 9, n)))
    return book(rows)


@pytest.mark.parametrize("cuts", [[1], [2500], [1, 2, 3, 4000], [4999]])
def test_chunked_equals_single_pass(cuts):
    b = random_book()
    edges = [0, *cuts, len(b)]
    chunks = [b.iloc[i:j] for i, j in zip(edges, edges[1:])]
    got = bucketize_chunks(iter(chunks), freq_s=10, tick=TICK, day0=DAY0)
    pd.testing.assert_frame_equal(got, bucketize(b, freq_s=10, tick=TICK))


def test_resample_1s_to_10s_equals_direct_10s():
    b = random_book()
    got = resample_buckets(bucketize(b, freq_s=1, tick=TICK), freq_s=10)
    pd.testing.assert_frame_equal(got, bucketize(b, freq_s=10, tick=TICK), check_exact=False, atol=1e-9)


def test_spread_ticks_is_state_at_bucket_end():
    rows = [(0.0, 100.0, 1, 100.1, 1), (4.0, 100.0, 1, 100.3, 1)]
    b = bucketize(book(rows), freq_s=10, tick=TICK)
    assert b.loc[DAY0, "spread_ticks"] == pytest.approx(3.0)
    assert b.loc[DAY0 + 50 * S, "spread_ticks"] == pytest.approx(3.0)


def test_trade_imbalance_signs_and_buckets():
    trades = pd.DataFrame({
        "timestamp": [DAY0 - 1000, DAY0 + 1 * S, DAY0 + 2 * S, DAY0 + 10 * S],
        "side": ["buy", "buy", "sell", "sell"],
        "amount": [9.0, 2.0, 0.5, 1.0],
    })
    ti = trade_imbalance(trades, day0=DAY0, freq_s=10)
    assert len(ti) == 8640
    assert ti.loc[DAY0] == pytest.approx(1.5)        # pre-midnight trade ignored
    assert ti.loc[DAY0 + 10 * S] == pytest.approx(-1.0)
    assert ti.loc[DAY0 + 20 * S] == 0


def test_trade_imbalance_ignores_unknown_side():
    trades = pd.DataFrame({"timestamp": [DAY0 + S, DAY0 + 2 * S], "side": ["buy", "unknown"], "amount": [2.0, 5.0]})
    assert trade_imbalance(trades, day0=DAY0, freq_s=10).loc[DAY0] == pytest.approx(2.0)


def test_resample_sums_trade_imbalance_when_present():
    b = bucketize(random_book(), freq_s=1, tick=TICK)
    b["ti"] = 1.0
    assert (resample_buckets(b, freq_s=10)["ti"] == 10.0).all()


# ---- Phase 4: receive clock, 100 ms buckets, mid level, funding overlap ----
from ofi.ofi import overlaps_funding


def test_100ms_buckets_and_mid_level():
    rows = [(-0.001, 100.0, 5, 100.1, 3), (0.05, 100.0, 8, 100.1, 3), (0.25, 100.1, 8, 100.2, 3)]
    b = bucketize(book(rows), freq_s=0.1, tick=TICK)
    assert len(b) == 864_000
    assert b.loc[DAY0, "ofi"] == pytest.approx(3.0)
    assert b.loc[DAY0, "mid"] == pytest.approx(100.05)
    assert b.loc[DAY0 + 200_000, "mid"] == pytest.approx(100.15)   # bucket [0.2, 0.3) s
    assert b.loc[DAY0 + 100_000, "mid"] == pytest.approx(100.05)   # empty bucket carries state


def test_bucketize_on_local_clock_uses_receive_time():
    df = book([(-0.001, 100.0, 5, 100.1, 3), (9.999, 100.0, 8, 100.1, 3)])
    df["local_timestamp"] = df["timestamp"] + 5_000  # received 5 ms later -> lands in next 10 s bucket
    b = bucketize(df, freq_s=10, tick=TICK, clock="local_timestamp")
    assert b.loc[DAY0, "ofi"] == 0
    assert b.loc[DAY0 + 10 * S, "ofi"] == pytest.approx(3.0)


def test_overlaps_funding_for_arbitrary_spans():
    t = lambda h, m, s=0: DAY0 + (h * 3600 + m * 60 + s) * S
    starts = np.array([t(7, 57, 0), t(7, 57, 0), t(12, 0), t(23, 57, 50)])
    ends = np.array([t(7, 58, 0), t(7, 58, 1), t(12, 1), t(23, 58, 0)])
    assert overlaps_funding(starts, ends).tolist() == [False, True, False, False]


def test_trade_imbalance_100ms_on_local_clock():
    trades = pd.DataFrame({"timestamp": [DAY0 + 50_000], "local_timestamp": [DAY0 + 120_000],
                           "side": ["buy"], "amount": [2.0]})
    ti = trade_imbalance(trades, day0=DAY0, freq_s=0.1, clock="local_timestamp")
    assert len(ti) == 864_000 and ti.loc[DAY0 + 100_000] == pytest.approx(2.0) and ti.loc[DAY0] == 0
