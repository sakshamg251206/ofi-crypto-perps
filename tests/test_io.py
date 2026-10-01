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


def test_load_trades_refuses_test_date(tmp_path):
    from ofi.io import load_trades
    with pytest.raises(HeldOutDateError):
        load_trades("BTCUSDT", "2026-05-01", data_dir=tmp_path)


import io as _io


class FakeResponse(_io.BytesIO):
    def __init__(self, body: bytes, declared: int):
        super().__init__(body)
        self.headers = {"Content-Length": str(declared)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_rejects_truncated_body(tmp_path, monkeypatch):
    import ofi.io as oio
    monkeypatch.setattr(oio.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(b"abc", declared=10))
    with pytest.raises(IOError):
        download_day("trades", "BTCUSDT", "2024-07-01", data_dir=tmp_path)
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_download_retries_then_succeeds(tmp_path, monkeypatch):
    import ofi.io as oio
    calls = iter([FakeResponse(b"abc", 10), FakeResponse(b"0123456789", 10)])
    monkeypatch.setattr(oio.urllib.request, "urlopen", lambda url, timeout=None: next(calls))
    p = download_day("trades", "BTCUSDT", "2024-07-01", data_dir=tmp_path)
    assert p.read_bytes() == b"0123456789"


def test_download_retries_after_connection_reset(tmp_path, monkeypatch):
    import ofi.io as oio
    state = {"n": 0}

    def flaky(url, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            raise ConnectionResetError(54, "Connection reset")
        return FakeResponse(b"0123456789", 10)

    monkeypatch.setattr(oio.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(oio.time, "sleep", lambda s: None)
    assert download_day("trades", "BTCUSDT", "2024-07-01", data_dir=tmp_path).read_bytes() == b"0123456789"


def test_test_dates_can_be_unlocked_only_explicitly():
    import ofi.io as oio
    with pytest.raises(HeldOutDateError):
        assert_not_test_date("2026-05-01")
    with oio.unlock_test_dates():
        assert_not_test_date("2026-05-01")
    with pytest.raises(HeldOutDateError):
        assert_not_test_date("2026-05-01")


def test_download_gives_up_with_the_underlying_error(tmp_path, monkeypatch):
    import ofi.io as oio
    seen = []

    def down(url, timeout=None):
        seen.append(timeout)
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(oio.urllib.request, "urlopen", down)
    monkeypatch.setattr(oio.time, "sleep", lambda s: None)
    with pytest.raises(OSError, match="failed after 4 attempts") as e:
        download_day("trades", "BTCUSDT", "2024-07-01", data_dir=tmp_path)
    assert isinstance(e.value.__cause__, ConnectionRefusedError)
    assert seen == [oio.TIMEOUT_S] * oio.MAX_ATTEMPTS  # never an unbounded wait
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_download_skips_files_already_on_disk(tmp_path, monkeypatch):
    import ofi.io as oio
    p = oio.raw_path("trades", "BTCUSDT", "2024-07-01", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"cached")
    monkeypatch.setattr(oio.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network used"))
    assert download_day("trades", "BTCUSDT", "2024-07-01", data_dir=tmp_path).read_bytes() == b"cached"
