"""Command-line entry point: `ofi <command>`. Run `ofi --help` for the pipeline overview."""
import argparse
import importlib
import sys

from ofi import __version__

# (command, module in ofi.pipeline, one-line help), in pipeline order.
COMMANDS = [
    ("status", "status", "show configuration and which data / results are present"),
    ("buckets", "buckets", "step 1: download a symbol's days and build 1 s buckets + quality reports"),
    ("phase1", "phase1", "pilot: H1 on 3 BTCUSDT days (in-memory, ~10 GB RAM)"),
    ("phase2", "phase2", "step 2: H1–H4 for one symbol (use --phase 3 for ETHUSDT/WLDUSDT)"),
    ("select-symbol", "select_symbol", "step 3: pre-registered third-symbol rule on 2023-08-01"),
    ("frames", "frames", "step 4: receive-clock prediction frames for H5/H6"),
    ("phase4", "phase4", "step 5: H5/H6 train / validation / walk-forward, freezes the models"),
    ("final-test", "final_test", "step 6: one-shot held-out test (already used; refuses to re-run)"),
    ("figures", "figures", "step 7: regenerate the memo figures"),
    ("site", "site", "export committed results for the results explorer (site/)"),
]

DESCRIPTION = """\
Order-flow imbalance (OFI) on Binance USDⓈ-M perpetuals: does it explain and does it predict price moves?

Pipeline (each step reads the previous step's output):
  ofi buckets --symbol BTCUSDT     download + bucket 31 days
  ofi phase2  --symbol BTCUSDT     H1–H4, writes reports/phase2_BTCUSDT.md
  ofi frames && ofi phase4         H5/H6 on train / validation days
  ofi figures                      memo figures

Start with `ofi status`.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ofi", description=DESCRIPTION,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="<command>")
    for name, module, help_text in COMMANDS:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(_module=module)
        try:
            _module(module).add_arguments(p)
        except ModuleNotFoundError as e:  # optional extra not installed (matplotlib for `figures`)
            p.set_defaults(_missing=e.name)
    return ap


def _module(name: str):
    return importlib.import_module(f"ofi.pipeline.{name}")


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 0
    if missing := getattr(args, "_missing", None):
        print(f"`ofi {args.command}` needs {missing}: pip install -e '.[figures]'", file=sys.stderr)
        return 1
    try:
        _module(args._module).run(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
