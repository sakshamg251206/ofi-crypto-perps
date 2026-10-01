import datetime as dt

from ofi.config import DATES, TEST, TRAIN, VALID, first_of_month


def test_first_of_month_spans_year_boundaries():
    assert first_of_month(dt.date(2023, 11, 1), dt.date(2024, 2, 1)) == [
        "2023-11-01", "2023-12-01", "2024-01-01", "2024-02-01"]
    assert first_of_month(dt.date(2023, 11, 2), dt.date(2023, 12, 31)) == ["2023-12-01"]


def test_sample_split_matches_the_pre_registration():
    assert len(DATES) == 31 and DATES[0] == "2023-09-01" and DATES[-1] == "2026-03-01"
    assert len(TRAIN) == 24 and len(VALID) == 7 and TRAIN + VALID == DATES
    assert TEST == ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
    assert not set(TEST) & set(DATES)
