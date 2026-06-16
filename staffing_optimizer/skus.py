"""SKU-level makespan lookup.

The base engine uses one makespan per department.  In practice the time to process a unit
depends on the SKU, and different SKUs flow through the network in different volumes.  This
module resolves work at the SKU level and collapses it back to an *effective* per-department
makespan that plugs into the same engine unchanged.

Given a makespan table ``m[k, i]`` (SKU k at department i) and exogenous SKU demand
``d[k, i]``, each SKU's throughput is ``lambda_k = (I - P)^-1 d_k`` (shared routing).  The
total work-time at department i is ``sum_k lambda_{k,i} * m[k, i]``, and the effective
makespan is that divided by total units — so ``staffing_requirement`` of the aggregated
network exactly reproduces the SKU-resolved work-time.

Usage::

    from staffing_optimizer import skus

    # sku_makespan[k, i] and sku_demand[k, i] are (n_sku x n_dept) arrays
    wl = skus.sku_workload(net, sku_makespan, sku_demand)        # effective makespan, FTE
    agg = skus.aggregate_network(net, sku_makespan, sku_demand)  # plugs into the same engine
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from staffing_optimizer.equilibrium import leontief_inverse
from staffing_optimizer.network import DepartmentNetwork


@dataclass
class SkuWorkload:
    departments: list[str]
    skus: list[str]
    per_sku_units: np.ndarray       # (n_sku, n_dept) throughput of each SKU at each department
    total_units: np.ndarray         # (n_dept,) throughput summed over SKUs
    work_time: np.ndarray           # (n_dept,) processing time per period
    effective_makespan: np.ndarray  # (n_dept,) work-time-weighted makespan
    required_fte: np.ndarray        # (n_dept,) work_time / T


def _as_tables(base_net: DepartmentNetwork, sku_makespan, sku_demand):
    sku_makespan = np.asarray(sku_makespan, dtype=float)
    sku_demand = np.asarray(sku_demand, dtype=float)
    n = base_net.n
    if sku_makespan.ndim != 2 or sku_makespan.shape[1] != n:
        raise ValueError(f"sku_makespan must be (n_sku, {n}); got {sku_makespan.shape}")
    if sku_demand.shape != sku_makespan.shape:
        raise ValueError("sku_makespan and sku_demand must have the same shape")
    if not np.all(np.isfinite(sku_makespan)) or np.any(sku_makespan <= 0):
        raise ValueError("sku makespans must be finite and strictly positive")
    if not np.all(np.isfinite(sku_demand)) or np.any(sku_demand < 0):
        raise ValueError("sku demand must be finite and non-negative")
    return sku_makespan, sku_demand


def sku_workload(base_net: DepartmentNetwork, sku_makespan, sku_demand, skus=None) -> SkuWorkload:
    """Resolve SKU-level throughput and the effective per-department makespan."""
    sku_makespan, sku_demand = _as_tables(base_net, sku_makespan, sku_demand)
    leontief = leontief_inverse(base_net)
    per_sku_units = (leontief @ sku_demand.T).T           # row k = (I - P)^-1 d_k
    total_units = per_sku_units.sum(axis=0)
    work_time = (per_sku_units * sku_makespan).sum(axis=0)
    effective = np.where(total_units > 0, work_time / np.where(total_units > 0, total_units, 1.0),
                         base_net.makespan)
    required = work_time / base_net.time_per_employee
    if skus is None:
        skus = [f"SKU{i + 1}" for i in range(sku_makespan.shape[0])]
    return SkuWorkload(
        departments=list(base_net.names),
        skus=list(skus),
        per_sku_units=per_sku_units,
        total_units=total_units,
        work_time=work_time,
        effective_makespan=effective,
        required_fte=required,
    )


def aggregate_network(
    base_net: DepartmentNetwork, sku_makespan, sku_demand, *, name: str | None = None
) -> DepartmentNetwork:
    """Build a single-makespan network whose work matches the SKU-resolved workload.

    The result reuses the base routing, headcount and congestion, with the effective makespan
    and the SKU-summed exogenous demand, so basis vectors, gaps and dynamics all apply directly.
    """
    workload = sku_workload(base_net, sku_makespan, sku_demand)
    aggregate_demand = np.asarray(sku_demand, dtype=float).sum(axis=0)
    return DepartmentNetwork(
        names=list(base_net.names),
        routing=base_net.routing.copy(),
        demand=aggregate_demand,
        makespan=workload.effective_makespan,
        time_per_employee=base_net.time_per_employee,
        headcount=base_net.headcount,
        congestion=None if base_net.congestion is None else base_net.congestion.copy(),
        name=name or (f"{base_net.name}+skus" if base_net.name else None),
    )
