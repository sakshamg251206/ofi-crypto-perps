import numpy as np
import pandas as pd
import pytest

from ofi.quality import quality_report

S = 1_000_000
DAY0 = 1_693_526_400 * S


def toy():
    # 6 rows; row 3 crossed (bid >= ask), row 4 timestamp goes backwards, row 5 has NaN ask size.
    sec = [0.0, 1.0, 2.0, 3.0, 2.5, 7200.0]
    df = pd.DataFrame({
        "timestamp": [DAY0 + int(s * S) for s in sec],
        "bid_price": [100.0, 100.0, 100.1, 100.3, 100.0, 100.0],
        "bid_amount": [1.0, 2, 3, 4, 5, 6],
        "ask_price": [100.1, 100.1, 100.3, 100.3, 100.1, 100.1],
        "ask_amount": [1.0, 1, 1, 1, 1, np.nan],
    })
    df["local_timestamp"] = df["timestamp"] + 5_000  # 5 ms receive delay
    df.loc[1, "local_timestamp"] = df.loc[1, "timestamp"] - 1_000  # clock skew on one row
    return df


def test_counts_defects():
    r = quality_report(toy(), tick=0.1)
    assert r["rows"] == 6
    assert r["crossed_or_locked"] == 1
    assert r["ts_backwards"] == 1
    assert r["rows_with_nan"] == 1


def test_infers_tick_and_spread_in_ticks():
    r = quality_report(toy(), tick=0.1)
    assert r["inferred_tick"] == pytest.approx(0.1)
    assert r["frac_spread_1tick"] == pytest.approx(3 / 5)  # rows 0,1,4 of the 5 valid rows are 1 tick


def test_receive_delay_and_negative_fraction():
    r = quality_report(toy(), tick=0.1)
    assert r["recv_delay_ms_p50"] == pytest.approx(5.0)
    assert r["frac_recv_delay_negative"] == pytest.approx(1 / 6)


def test_max_gap_and_rows_per_hour():
    r = quality_report(toy(), tick=0.1)
    assert r["max_gap_s"] == pytest.approx(7200 - 3.0)
    assert r["rows_per_hour"][0] == 5 and r["rows_per_hour"][2] == 1


from ofi.quality import QualityAccumulator


def test_consecutive_duplicates_counted():
    df = toy()
    df = pd.concat([df.iloc[:2], df.iloc[[1]], df.iloc[2:]], ignore_index=True)  # repeat row 1
    assert quality_report(df, tick=0.1)["duplicate_rows"] == 1


@pytest.mark.parametrize("cut", [1, 3, 4, 5])
def test_chunked_report_equals_whole(cut):
    df = toy()
    df = pd.concat([df.iloc[:2], df.iloc[[1]], df.iloc[2:]], ignore_index=True)
    acc = QualityAccumulator(tick=0.1)
    acc.update(df.iloc[:cut])
    acc.update(df.iloc[cut:])
    assert acc.report() == quality_report(df, tick=0.1)


def test_off_grid_rows_counted():
    df = toy()
    df.loc[2, "ask_price"] = 100.33  # not a multiple of the 0.1 tick
    assert quality_report(df, tick=0.1)["off_grid_rows"] == 1
    assert quality_report(toy(), tick=0.1)["off_grid_rows"] == 0


from ofi.quality import infer_tick


@pytest.mark.parametrize("prices, tick", [
    ([100.0, 100.1, 100.3, 99.9], 0.1),
    ([2466.03, 2466.04, 2466.1], 0.01),
    ([0.25015, 0.25020, 0.25025], 0.00005),
    ([105.0, 110.0, 125.0], 5.0),
    ([1.0, 2.0, 4.0], 1.0),
])
def test_infer_tick(prices, tick):
    assert infer_tick(np.array(prices)) == pytest.approx(tick)


def test_infer_tick_ignores_rare_off_grid_prices():
    prices = np.r_[np.arange(10_000) * 0.1 + 30_000, 34_417.43]  # 1 off-grid in 10,001
    assert infer_tick(prices) == pytest.approx(0.1)


def test_infer_tick_tiny_prices_not_fooled_by_rounding_to_zero():
    # 1000PEPEUSDT-like prices: ~0.0013 with tick 1e-7; any huge t makes price/t round to 0.
    prices = np.array([0.0013012, 0.0013013, 0.0013015, 0.0012999])
    assert infer_tick(prices) == pytest.approx(1e-7)
