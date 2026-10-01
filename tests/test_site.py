"""The results-explorer export must reproduce the committed reports exactly."""
import argparse
import json

import pytest

from ofi.pipeline import site


@pytest.fixture(scope="module")
def data():
    return site.build()


def test_md_tables_groups_by_heading(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("# T\n\n| a | b \\| c |\n|---|---|\n| 1 | 2 |\n\n## Next\n\n| x |\n|---|\n| 9 |\n")
    t = site.md_tables(p)
    assert list(t) == ["T", "Next"]
    assert t["T"][0].columns.tolist() == ["a", "b \\| c"] and t["T"][0].iloc[0].tolist() == ["1", "2"]
    assert t["Next"][0]["x"].tolist() == ["9"]


def test_headline_numbers_match_the_memo(data):
    c, p = data["contemporaneous"], data["predictive"]
    assert [c[s]["r2"][0] for s in data["symbols"]] == [0.71, 0.685, 0.725]
    assert {s: c[s]["verdicts"]["H3"] for s in data["symbols"]} == {"BTCUSDT": "FAIL", "ETHUSDT": "PASS",
                                                                      "WLDUSDT": "PASS"}
    assert c["WLDUSDT"]["verdicts"]["H2"] == "FAIL"
    assert all(p[s]["verdict"] == "FAIL" for s in data["symbols"])
    assert p["BTCUSDT"]["oos_r2"] == [-0.0008, -0.0023, 0.0008]
    assert data["fee_bps"] == 5.0


def test_h3_point_fit_and_quintiles_reproduce_the_reports(data):
    assert data["explore"]["BTCUSDT"]["depth_fit"]["lam"] == pytest.approx(0.744, abs=5e-4)
    assert data["explore"]["WLDUSDT"]["spread_quintiles"]["r2"] == pytest.approx([0.837, 0.806, 0.78, 0.61, 0.508],
                                                                                  abs=5e-4)
    assert len(data["explore"]["ETHUSDT"]["per_day"]) == 31


def test_export_is_deterministic_and_matches_committed_file(tmp_path):
    out = tmp_path / "data.js"
    site.run(argparse.Namespace(out=out))
    text = out.read_text()
    json.loads(text.split("=", 1)[1].strip().rstrip(";"))
    assert text == (site.SITE_DIR / "data.js").read_text(), "site/data.js is stale: run `ofi site`"
