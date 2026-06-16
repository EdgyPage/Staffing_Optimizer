"""Validate a design file, report its mathematical soundness, and draw the system diagram.

Examples::

    python design.py examples/warehouse_5dept.flow
    python design.py examples/warehouse_5dept.flow --image
    python design.py examples/warehouse_5dept.flow --to-yaml scenario.yaml

Writes a Graphviz `.dot` and a Mermaid `.mmd` next to the input by default; `--image` also
writes a `.png` (needs the `viz` extra). Exit code is 1 if the design has any errors.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from staffing_optimizer.diagnostics import Severity
from staffing_optimizer.diagram import DiagramModel, render_image, to_dot, to_mermaid
from staffing_optimizer.dsl import parse_design
from staffing_optimizer.io_scenario import save_scenario


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate a warehouse design and draw its diagram.")
    parser.add_argument("design", help="path to a .flow design file")
    parser.add_argument("--image", action="store_true", help="also render a PNG diagram (needs the viz extra)")
    parser.add_argument("--no-dot", action="store_true", help="do not write the .dot file")
    parser.add_argument("--no-mermaid", action="store_true", help="do not write the .mmd file")
    parser.add_argument("--to-yaml", metavar="OUT", help="convert the design to an engine YAML scenario")
    args = parser.parse_args(argv)

    path = Path(args.design)
    result = parse_design(path.read_text(encoding="utf-8"), name=path.stem)

    counts = {sev: sum(1 for d in result.diagnostics if d.severity == sev) for sev in Severity}
    print(f"Design: {path.name}")
    for diag in result.diagnostics:
        print(f"  {diag}")
    if not result.diagnostics:
        print("  (no diagnostics)")
    verdict = "SOUND" if result.ok else "NOT SOUND"
    print(f"  -> {verdict}  ({counts[Severity.ERROR]} error(s), {counts[Severity.WARNING]} warning(s))")

    model = DiagramModel.from_network(result.network) if result.network else DiagramModel.from_parse(result)
    if not args.no_dot:
        target = path.with_suffix(".dot")
        target.write_text(to_dot(model), encoding="utf-8")
        print(f"  wrote {target.name}")
    if not args.no_mermaid:
        target = path.with_suffix(".mmd")
        target.write_text(to_mermaid(model), encoding="utf-8")
        print(f"  wrote {target.name}")
    if args.image:
        target = path.with_suffix(".png")
        try:
            render_image(model, str(target))
            print(f"  wrote {target.name}")
        except RuntimeError as exc:
            print(f"  [image skipped] {exc}")
    if args.to_yaml:
        if result.network is None:
            print("  [yaml skipped] design is not sound enough to convert")
        else:
            save_scenario(result.network, args.to_yaml)
            print(f"  wrote {args.to_yaml}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
