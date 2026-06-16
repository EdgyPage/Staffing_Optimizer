"""Human-readable, headless report: throughput, staffing split, feasibility and gap table.

Used by ``solve.py`` and handy in tests/notebooks.  Pure text — no third-party deps beyond
numpy — so it works without the dashboard stack installed.

Usage::

    from staffing_optimizer.report import format_report

    print(format_report(net, headcount=20))      # throughput, split, feasibility summary
    print(format_report(net, actual=[12, 9]))    # adds actual / gap / status columns
"""
from __future__ import annotations

from staffing_optimizer.equilibrium import (
    staffing_requirement,
    staffing_split,
    throughput,
)
from staffing_optimizer.gaps import feasibility, gap_report, suggested_allocation
from staffing_optimizer.network import DepartmentNetwork


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def format_report(net: DepartmentNetwork, actual=None, headcount: float | None = None) -> str:
    """Render the equilibrium report.

    - Always shows throughput, required FTE and the staffing split.
    - If a headcount ``S`` is known, adds a suggested allocation column and a feasibility line.
    - If an ``actual`` staffing vector is given, adds actual / gap / status columns instead.
    """
    pool = headcount if headcount is not None else net.headcount
    lam = throughput(net)
    required = staffing_requirement(net)
    split = staffing_split(net)
    name_w = max(8, max((len(x) for x in net.names), default=8))

    use_actual = actual is not None
    use_suggested = (not use_actual) and (pool is not None)
    if use_actual:
        rows = gap_report(net, actual)
    elif use_suggested:
        suggested = suggested_allocation(net, pool)

    header = f"{'Dept':<{name_w}}  {'lambda':>10}  {'req FTE':>9}  {'split':>7}"
    if use_suggested:
        header += f"  {'suggest':>9}"
    if use_actual:
        header += f"  {'actual':>9}  {'gap FTE':>9}  {'status':>7}"

    title = net.name or "network"
    roots = ", ".join(net.root_names()) or "(none)"
    meta = (
        f"n={net.n} departments | roots: {roots} | "
        f"spectral radius {net.spectral_radius():.3f} | T={net.time_per_employee:g}"
    )
    if pool is not None:
        meta += f" | S={pool:g}"

    lines = [f"Staffing equilibrium - {title}", meta, "", header, "-" * len(header)]
    for i, nm in enumerate(net.names):
        line = f"{nm:<{name_w}}  {lam[i]:>10.2f}  {required[i]:>9.2f}  {_pct(split[i]):>7}"
        if use_suggested:
            line += f"  {suggested[i]:>9.2f}"
        if use_actual:
            row = rows[i]
            line += f"  {row.actual_fte:>9.2f}  {row.gap_fte:>+9.2f}  {row.status:>7}"
        lines.append(line)

    if pool is not None:
        feas = feasibility(net, pool)
        verdict = "FEASIBLE" if feas["feasible"] else "INFEASIBLE"
        extra = (
            f"{pool - feas['required_fte']:.1f} FTE spare"
            if feas["feasible"]
            else f"short {feas['shortfall_fte']:.1f} FTE"
        )
        lines += [
            "",
            (
                f"System: required {feas['required_fte']:.1f} FTE vs {pool:g} available "
                f"-> utilization {_pct(feas['utilization'])} -> {verdict} ({extra})"
            ),
        ]
    return "\n".join(lines)
