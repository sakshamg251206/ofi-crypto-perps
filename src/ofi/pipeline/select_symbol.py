"""Apply the pre-registered third-symbol rule to 2023-08-01 data only (docs/DECISIONS.md, 2026-10-01).

Run: ofi select-symbol
Output: reports/third_symbol_selection.md
"""
import argparse
import io
import re
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ofi.config import REPORTS_DIR
from ofi.pipeline.buckets import day_buckets

TIMEOUT_S = 60
DATE = "2023-08-01"
LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/daily/klines/"
KLINE_URL = "https://data.binance.vision/data/futures/um/daily/klines/{s}/1d/{s}-1d-{d}.zip"
EXCLUDE = {"BTCUSDT", "ETHUSDT"}


def list_symbols() -> list[str]:
    """All USDⓈ-M kline directories on data.binance.vision (paginated S3 listing)."""
    syms, marker = [], ""
    while True:
        xml = urllib.request.urlopen(f"{LIST_URL}&marker={marker}", timeout=TIMEOUT_S).read().decode()
        syms += re.findall(r"<Prefix>data/futures/um/daily/klines/([^/<]+)/</Prefix>", xml)
        m = re.search(r"<NextMarker>([^<]+)</NextMarker>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml or not m:
            return syms
        marker = m.group(1)


def quote_volume(symbol: str) -> float | None:
    """2023-08-01 daily quote volume (USDT), or None if the symbol had no kline that day."""
    try:
        raw = urllib.request.urlopen(KLINE_URL.format(s=symbol, d=DATE), timeout=TIMEOUT_S).read()
    except urllib.error.HTTPError:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode()
    first = text.splitlines()[0].split(",")
    row = text.splitlines()[1].split(",") if first[0] == "open_time" else first  # older files have no header
    return float(row[7])  # column 7 = quote_volume


def add_arguments(ap: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> None:
    perps = [s for s in list_symbols() if re.fullmatch(r"[A-Z0-9]+USDT", s) and s not in EXCLUDE]
    with ThreadPoolExecutor(16) as ex:
        vols = dict(zip(perps, ex.map(quote_volume, perps)))
    ranked = sorted(((v, s) for s, v in vols.items() if v is not None), reverse=True)
    top = [s for _, s in ranked[:20]]
    print(f"{len(perps)} USDT perps listed, {sum(v is not None for v in vols.values())} traded on {DATE}", flush=True)

    rows = []
    for s in top:
        b, q, _ = day_buckets(s, DATE)
        rows.append({"symbol": s, "quote_volume_musd": vols[s] / 1e6, "tick": q["tick"],
                     "frac_spread_gt1": float((b["spread_ticks"] > 1).mean()),
                     "median_updates_per_s": float(b["n_events"].median()), "rows": q["rows"]})
        print(rows[-1], flush=True)
    t = pd.DataFrame(rows)
    t["eligible"] = t["median_updates_per_s"] >= 1
    t = t.sort_values(["eligible", "frac_spread_gt1", "quote_volume_musd"], ascending=False)
    pick = t[t["eligible"]].iloc[0]["symbol"]

    lines = [f"# Third-symbol selection on {DATE} (pre-sample)", "",
             "Rule: HYPOTHESES.md; operational details: DECISIONS.md (2026-10-01).", "",
             f"**Selected: {pick}**", "", "| " + " | ".join(t.columns) + " |", "|" + "---|" * len(t.columns)]
    lines += ["| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in r) + " |"
              for r in t.itertuples(index=False)]
    (REPORTS_DIR / "third_symbol_selection.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
