import numpy as np
import pandas as pd
import pytest

from ofi.ofi import bucketize
from ofi.predict import fit_ols, oos_r2, predictive_frame, sign_strategy_pnl

S = 1_000_000
DAY0 = 1_693_526_400 * S
TICK = 0.1


def local_book(rows):
    """rows: (receive seconds after DAY0, bid_px, bid_sz, ask_px, ask_sz); exchange ts 2 ms earlier."""
    df = pd.DataFrame(rows, columns=["sec", "bid_price", "bid_amount", "ask_price", "ask_amount"])
    df["local_timestamp"] = DAY0 + (df.pop("sec") * S).round().astype("int64")
    df["timestamp"] = df["local_timestamp"] - 2_000
    return df


NOON = 12 * 3600  # away from funding exclusions
T0 = DAY0 + NOON * S


@pytest.fixture
def frame():
    rows = [(-0.001, 100.0, 5, 100.1, 3),
            (NOON + 5.0, 100.0, 8, 100.1, 3),      # OFI +3 in [12:00:00, 12:00:10)
            (NOON + 10.05, 100.1, 8, 100.2, 3)]    # mid +1 tick at +10.05 s; e = +8 +3 = +11 in [+10, +20)
    b100 = bucketize(local_book(rows), freq_s=0.1, tick=TICK, clock="local_timestamp")
    b100["ti"] = 0.0
    return predictive_frame(b100, tick=TICK, freq_s=10, latencies_ms=(0, 100, 500))


def test_feature_is_ofi_of_previous_bucket(frame):
    assert frame.loc[T0 + 10 * S, "x"] == pytest.approx(3.0)
    assert frame.loc[T0 + 20 * S, "x"] == pytest.approx(11.0)


def test_target_respects_latency(frame):
    # move at +10.05 s is inside [+10, +20) at L=0 but before the +10.1 s entry at L=100 ms
    assert frame.loc[T0 + 10 * S, "y_0"] == pytest.approx(1.0)
    assert frame.loc[T0 + 10 * S, "y_100"] == pytest.approx(0.0)
    assert frame.loc[T0 + 10 * S, "y_500"] == pytest.approx(0.0)


def test_target_interval_never_overlaps_feature_interval(frame):
    for L in (0, 100, 500):
        assert (frame[f"tgt_start_{L}"] >= frame["feat_end"]).all()
        assert (frame["feat_end"] - frame["feat_start"] == 10 * S).all()


def test_funding_spans_dropped_with_exact_boundaries():
    rows = [(-0.001, 100.0, 5, 100.1, 3), (5.0, 100.0, 8, 100.1, 3)]
    b100 = bucketize(local_book(rows), freq_s=0.1, tick=TICK, clock="local_timestamp")
    b100["ti"] = 0.0
    f = predictive_frame(b100, tick=TICK, freq_s=10, latencies_ms=(0, 100, 500))
    sec = (f.index - DAY0) // S
    assert sec.min() == 130                                  # [t_{k-1}, ...) must start >= 00:02:00
    assert 7 * 3600 + 57 * 60 + 40 in set(sec)               # span ends 07:57:50.5 <= 07:58:00
    assert 7 * 3600 + 57 * 60 + 50 not in set(sec)           # span ends 07:58:00.5 > 07:58:00
    assert sec.max() == 23 * 3600 + 57 * 60 + 40             # last span must end <= 23:58:00


def test_entry_half_spread_in_bps(frame):
    # spread 1 tick = 0.1 at mid 100.05 -> half spread = 0.05 / 100.05 * 1e4 bps
    assert frame.loc[T0 + 10 * S, "half_spread_bps_0"] == pytest.approx(0.05 / 100.05 * 1e4)


def test_fit_ols_and_oos_r2():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    a, b = fit_ols(x, 2.0 + 0.5 * x)
    assert (a, b) == pytest.approx((2.0, 0.5))
    y = np.array([1.0, -1.0])
    assert oos_r2(y, np.zeros(2)) == 0
    assert oos_r2(y, y) == 1
    assert oos_r2(y, -y) == pytest.approx(-3.0)


def strat_frame(y, yhat, t_idx=None, mid=100.0, hs=0.0):
    t = DAY0 + 10 * S * np.asarray(t_idx if t_idx is not None else np.arange(1, len(y) + 1))
    return pd.DataFrame({"y": y, "yhat": yhat, "mid_entry": mid, "half_spread_bps": hs}, index=pd.Index(t, name="t"))


def test_strategy_perfect_alternating_signal():
    y = np.array([1.0, -1.0, 1.0, -1.0])  # each move 0.1/100 = 10 bps
    r = sign_strategy_pnl(strat_frame(y, y), tick=TICK, fee_bps=1.0, freq_s=10)
    assert r["gross_bps"] == pytest.approx(40.0)
    assert r["turnover"] == 8                  # open 1 + three flips of 2 + close 1
    assert r["break_even_bps"] == pytest.approx(5.0)
    assert r["net_bps"] == pytest.approx(40.0 - 8 * 1.0)


def test_strategy_constant_position_and_spread_cost():
    y = np.array([1.0, 1.0, 1.0])
    r = sign_strategy_pnl(strat_frame(y, np.ones(3), hs=2.0), tick=TICK, fee_bps=0.0, freq_s=10)
    assert r["turnover"] == 2 and r["break_even_bps"] == pytest.approx(15.0)
    assert r["net_bps"] == pytest.approx(30.0 - 2 * 2.0)


def test_strategy_closes_position_across_gaps():
    y = np.array([1.0, 1.0])
    r = sign_strategy_pnl(strat_frame(y, np.ones(2), t_idx=[1, 5]), tick=TICK, fee_bps=0.0, freq_s=10)
    assert r["turnover"] == 4


def test_random_signal_breaks_even_near_zero():
    rng = np.random.default_rng(0)
    y = rng.standard_normal(200_000)
    r = sign_strategy_pnl(strat_frame(y, rng.standard_normal(200_000)), tick=TICK, fee_bps=0.0, freq_s=10)
    assert abs(r["break_even_bps"]) < 0.1
