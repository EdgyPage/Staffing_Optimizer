"""Static equilibrium: throughput, basis vectors, staffing requirement and split.

Flow balance gives each department's required throughput::

    lambda = d + P @ lambda      =>      lambda = (I - P)^-1 @ d

The staffing *basis matrix* maps demand to required full-time-equivalents (FTE)::

    M = (1 / T) * diag(m) @ (I - P)^-1          s_star = M @ d

Each column ``M[:, j]`` is a basis vector: the staffing footprint across *all* departments
caused by one unit of exogenous demand at node *j*.  Required staffing for any demand plan
is the matching linear combination of those columns.

Usage::

    from staffing_optimizer import equilibrium as eq

    eq.throughput(net)           # lambda: required throughput per department
    eq.basis_matrix(net)         # M: columns are per-root staffing basis vectors
    eq.staffing_requirement(net) # s* = M @ d: minimum FTE per department
    eq.staffing_split(net)       # balanced staffing as fractions summing to 1
"""
from __future__ import annotations

import numpy as np

from staffing_optimizer.network import DepartmentNetwork


def _solve(net: DepartmentNetwork, b: np.ndarray) -> np.ndarray:
    """Solve (I - P) x = b.  Preferred over an explicit inverse for stability."""
    identity = np.eye(net.n)
    return np.linalg.solve(identity - net.routing, b)


def throughput(net: DepartmentNetwork) -> np.ndarray:
    """Required throughput ``lambda`` per department (units/period) at equilibrium."""
    return _solve(net, net.demand)


def leontief_inverse(net: DepartmentNetwork) -> np.ndarray:
    """The fundamental matrix ``(I - P)^-1``; entry [i, j] = visits to i per unit demand at j."""
    return _solve(net, np.eye(net.n))


def basis_matrix(net: DepartmentNetwork) -> np.ndarray:
    """Staffing basis matrix ``M``; each column is a per-node staffing basis vector (FTE)."""
    leontief = leontief_inverse(net)
    return (net.makespan[:, None] * leontief) / net.time_per_employee


def staffing_requirement(net: DepartmentNetwork) -> np.ndarray:
    """Minimum FTE per department to keep inflow balanced: ``s* = m * lambda / T``."""
    return net.makespan * throughput(net) / net.time_per_employee


def staffing_split(net: DepartmentNetwork) -> np.ndarray:
    """Equilibrium staffing expressed as fractions summing to 1 (zeros if there is no work)."""
    required = staffing_requirement(net)
    total = required.sum()
    if total <= 0:
        return np.zeros_like(required)
    return required / total


def allocate_headcount(net: DepartmentNetwork, headcount: float | None = None) -> np.ndarray:
    """Distribute a closed pool ``S`` across departments by the equilibrium split."""
    pool = headcount if headcount is not None else net.headcount
    if pool is None:
        raise ValueError("headcount must be provided (argument or on the network)")
    return staffing_split(net) * pool
