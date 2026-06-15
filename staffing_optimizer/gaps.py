"""Staffing shorts and feasibility against a closed headcount.

Given the equilibrium requirement ``s*`` and an *actual* staffing vector ``s``, the gap
``s*_i - s_i`` is positive when a department is short (its backlog will grow) and negative
when it has slack.  Multiplying by ``T`` re-expresses the gap as work-time per period, which
is how a shortfall is communicated to operations ("Picking is ~1,500 minutes/shift short").
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from staffing_optimizer.equilibrium import (
    staffing_requirement,
    staffing_split,
    throughput,
)
from staffing_optimizer.network import DepartmentNetwork

_STATUS_TOL = 1e-6


@dataclass
class GapRow:
    name: str
    throughput: float     # lambda_i (units/period)
    required_fte: float   # s*_i
    actual_fte: float     # s_i
    gap_fte: float        # s*_i - s_i  (>0 short, <0 slack)
    gap_time: float       # gap_fte * T (work-time/period short)
    status: str           # "SHORT", "OK", or "SLACK"


def staffing_gaps(net: DepartmentNetwork, actual) -> np.ndarray:
    """Vector of ``s* - s`` (positive = short, negative = slack)."""
    actual = np.asarray(actual, dtype=float)
    return staffing_requirement(net) - actual


def feasibility(net: DepartmentNetwork, headcount: float | None = None) -> dict:
    """System-level feasibility of meeting the equilibrium requirement with the pool ``S``."""
    pool = headcount if headcount is not None else net.headcount
    required = float(staffing_requirement(net).sum())
    out = {"required_fte": required, "headcount": pool}
    if pool is None:
        out.update(utilization=None, feasible=None, shortfall_fte=None)
    else:
        out.update(
            utilization=required / pool,
            feasible=required <= pool + _STATUS_TOL,
            shortfall_fte=max(0.0, required - pool),
        )
    return out


def gap_report(net: DepartmentNetwork, actual, tol: float = _STATUS_TOL) -> list[GapRow]:
    """Per-department gap rows comparing the equilibrium requirement to ``actual`` staffing."""
    actual = np.asarray(actual, dtype=float)
    if actual.shape != (net.n,):
        raise ValueError(f"actual staffing must have length {net.n}, got {actual.shape}")
    lam = throughput(net)
    required = staffing_requirement(net)
    rows: list[GapRow] = []
    for i, name in enumerate(net.names):
        gap = float(required[i] - actual[i])
        if gap > tol:
            status = "SHORT"
        elif gap < -tol:
            status = "SLACK"
        else:
            status = "OK"
        rows.append(
            GapRow(
                name=name,
                throughput=float(lam[i]),
                required_fte=float(required[i]),
                actual_fte=float(actual[i]),
                gap_fte=gap,
                gap_time=gap * net.time_per_employee,
                status=status,
            )
        )
    return rows


def suggested_allocation(net: DepartmentNetwork, headcount: float | None = None) -> np.ndarray:
    """Allocate the closed pool ``S``.

    When feasible, cover each department's requirement exactly, then place the spare capacity
    as a buffer toward the most congestion-prone departments (those with the largest
    ``congestion`` coefficients, falling back to the requirement weighting).  When infeasible,
    allocate proportionally to the requirement.  The result always sums to ``S``.
    """
    pool = headcount if headcount is not None else net.headcount
    if pool is None:
        raise ValueError("headcount must be provided (argument or on the network)")
    required = staffing_requirement(net)
    total = required.sum()
    if total >= pool:  # infeasible or exactly tight -> proportional to requirement
        return staffing_split(net) * pool
    slack = pool - total
    if net.congestion is not None and net.congestion.sum() > 0:
        weights = net.congestion
    elif total > 0:
        weights = required
    else:
        weights = np.ones(net.n)
    return required + slack * (weights / weights.sum())
