import csv

import pytest

from ofi.io import HeldOutDateError, assert_not_test_date, download_day, load_top_of_book
from ofi.ledger import log_run


@pytest.mark.parametrize("d", ["2026-04-01", "2026-06-01", "2026-09-01"])
def test_guard_rejects_test_split_dates(d):
    with pytest.raises(HeldOutDateError):
        assert_not_test_date(d)


@pytest.mark.parametrize("d", ["2023-09-01", "2025-09-01", "2026-03-01"])
def test_guard_allows_train_and_validation_dates(d):
    assert_not_test_date(d)


def test_download_refuses_test_date_before_any_network_call(tmp_path):
    with pytest.raises(HeldOutDateError):
        download_day("book_ticker", "BTCUSDT", "2026-05-01", data_dir=tmp_path)
    assert not any(tmp_path.iterdir())


def test_load_refuses_test_date(tmp_path):
    with pytest.raises(HeldOutDateError):
        load_top_of_book("book_ticker", "BTCUSDT", "2026-05-01", data_dir=tmp_path)


def test_ledger_appends_row_under_existing_header(tmp_path):
    p = tmp_path / "ledger.csv"
    p.write_text("run_utc,git_sha,phase,metric,value\n")
    log_run(p, phase="1", metric="median_r2", value=0.3)
    rows = list(csv.DictReader(p.open()))
    assert len(rows) == 1
    assert rows[0]["phase"] == "1" and rows[0]["value"] == "0.3"
    assert rows[0]["run_utc"] and rows[0]["git_sha"]


def test_ledger_rejects_unknown_field(tmp_path):
    p = tmp_path / "ledger.csv"
    p.write_text("run_utc,git_sha,metric\n")
    with pytest.raises(KeyError):
        log_run(p, nonsense=1)
