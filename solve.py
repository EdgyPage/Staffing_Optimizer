"""Headless entry point: print the staffing equilibrium report for a scenario.

Examples::

    python solve.py
    python solve.py examples/warehouse_5dept.yaml
    python solve.py examples/warehouse_5dept.yaml --headcount 45
    python solve.py examples/warehouse_5dept.yaml --actual 15,11,10,7,4
"""
from __future__ import annotations

import argparse
from pathlib import Path

from staffing_optimizer.io_scenario import load_scenario
from staffing_optimizer.report import format_report

DEFAULT_SCENARIO = Path(__file__).parent / "examples" / "warehouse_5dept.yaml"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Warehouse staffing equilibrium report")
    parser.add_argument(
        "scenario", nargs="?", default=str(DEFAULT_SCENARIO), help="path to a scenario YAML file"
    )
    parser.add_argument(
        "--headcount", type=float, default=None, help="override the closed headcount S"
    )
    parser.add_argument(
        "--actual", type=str, default=None, help="comma-separated actual FTE per department"
    )
    args = parser.parse_args(argv)

    net = load_scenario(args.scenario)
    actual = [float(x) for x in args.actual.split(",")] if args.actual else None
    print(format_report(net, actual=actual, headcount=args.headcount))


if __name__ == "__main__":
    main()
