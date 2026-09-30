import numpy as np
import pandas as pd
import pytest

from ofi.ofi import compute_e

# Previous state for every toy case: bid 100.0 x 5, ask 100.3 x 3 (tick 0.1).
PREV = (100.0, 5.0, 100.3, 3.0)


def two_rows(new):
    """Book with the shared previous state followed by one new state."""
    rows = [PREV, new]
    return pd.DataFrame(rows, columns=["bid_price", "bid_amount", "ask_price", "ask_amount"])


@pytest.mark.parametrize(
    "new, expected",
    [
        ((100.0, 8.0, 100.3, 3.0), +3.0),  # bid size grows at same price
        ((100.0, 5.0, 100.3, 7.0), -4.0),  # ask size grows at same price
        ((100.1, 2.0, 100.3, 3.0), +2.0),  # bid improves: new queue counts, old ignored
        ((99.9, 4.0, 100.3, 3.0), -5.0),   # bid depleted: old queue removed
        ((100.0, 5.0, 100.2, 1.0), -1.0),  # ask improves
        ((100.0, 5.0, 100.4, 6.0), +3.0),  # ask depleted
        ((100.0, 2.0, 100.4, 9.0), 0.0),   # both sides change, cancel out
    ],
)
def test_e_matches_hand_computed_cases(new, expected):
    e = compute_e(two_rows(new))
    assert e.iloc[1] == pytest.approx(expected)


def test_first_row_is_nan():
    e = compute_e(two_rows((100.0, 8.0, 100.3, 3.0)))
    assert np.isnan(e.iloc[0])


def test_e_telescopes_when_prices_never_change():
    # With fixed prices, sum of e_n = change in bid size - change in ask size.
    rng = np.random.default_rng(0)
    n = 50
    df = pd.DataFrame({
        "bid_price": 100.0, "bid_amount": rng.uniform(1, 10, n),
        "ask_price": 100.1, "ask_amount": rng.uniform(1, 10, n),
    })
    expected = (df.bid_amount.iloc[-1] - df.bid_amount.iloc[0]) - (df.ask_amount.iloc[-1] - df.ask_amount.iloc[0])
    assert compute_e(df).sum() == pytest.approx(expected)
