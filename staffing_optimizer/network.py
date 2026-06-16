"""Department network model: routing matrix, demand, makespan, and validation.

A warehouse is modeled as ``n`` departments that hand work to one another in fixed ratios.
The routing matrix ``P`` captures those ratios: ``P[i, j]`` is the fraction of department
*j*'s completed output that becomes new work for department *i*.  Departments with no
internal inflow (an all-zero routing *row*) are *root* nodes and receive only exogenous
demand ``d`` (e.g. inbound trucks / customer orders).

All quantities are per-period.  ``makespan`` is processing-time-per-unit per employee;
``time_per_employee`` (T) is the productive time one employee supplies per period, so a
department's processing-time requirement converts to full-time-equivalents (FTE) by
dividing work-time by T.

Usage::

    from staffing_optimizer.network import DepartmentNetwork

    net = DepartmentNetwork(
        names=["Receiving", "Picking"],
        routing=[[0.0, 0.0], [1.0, 0.0]],     # Receiving -> Picking
        demand=[1000, 0], makespan=[2.0, 1.0],
        time_per_employee=480, headcount=20,
    )
    net.root_names()        # ['Receiving']
    net.spectral_radius()   # must be < 1, else construction raises ValueError
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A network is "unstable" when rework amplifies forever, i.e. the spectral radius of the
# routing matrix reaches 1.  We reject anything within this tolerance of 1.
_SPECTRAL_TOL = 1e-9


@dataclass
class DepartmentNetwork:
    """A network of departments with work-routing ratios, demand and makespan.

    Constructing an instance validates it; an invalid network raises ``ValueError``.
    """

    names: list[str]
    routing: np.ndarray              # P, shape (n, n); P[i, j] = fraction of j's output sent to i
    demand: np.ndarray               # d, shape (n,); exogenous arrivals per period
    makespan: np.ndarray             # m, shape (n,); processing time per unit, per employee
    time_per_employee: float = 1.0   # T; productive time per employee per period (units match makespan)
    headcount: float | None = None   # S; total closed pool of employees (optional)
    congestion: np.ndarray | None = None  # beta, shape (n,); exponential backlog coefficients (dynamics)
    buffer_capacity: np.ndarray | None = None  # B_max, shape (n,); max backlog before backpressure (inf = unbounded)
    name: str | None = None          # optional scenario label, for reports/UI

    def __post_init__(self) -> None:
        self.names = list(self.names)
        self.routing = np.asarray(self.routing, dtype=float)
        self.demand = np.asarray(self.demand, dtype=float)
        self.makespan = np.asarray(self.makespan, dtype=float)
        if self.congestion is not None:
            self.congestion = np.asarray(self.congestion, dtype=float)
        if self.buffer_capacity is not None:
            self.buffer_capacity = np.asarray(self.buffer_capacity, dtype=float)
        self.validate()

    # -- structure -------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.names)

    def index(self, name: str) -> int:
        return self.names.index(name)

    # -- validation ------------------------------------------------------------
    def validate(self) -> None:
        n = self.n
        if self.routing.shape != (n, n):
            raise ValueError(f"routing must be {n}x{n}, got {self.routing.shape}")
        if self.demand.shape != (n,):
            raise ValueError(f"demand must have length {n}, got {self.demand.shape}")
        if self.makespan.shape != (n,):
            raise ValueError(f"makespan must have length {n}, got {self.makespan.shape}")
        if self.congestion is not None and self.congestion.shape != (n,):
            raise ValueError(f"congestion must have length {n}, got {self.congestion.shape}")
        if self.buffer_capacity is not None and self.buffer_capacity.shape != (n,):
            raise ValueError(f"buffer_capacity must have length {n}, got {self.buffer_capacity.shape}")

        if not np.all(np.isfinite(self.routing)) or np.any(self.routing < 0):
            raise ValueError("routing entries must be finite and non-negative")
        if not np.all(np.isfinite(self.demand)) or np.any(self.demand < 0):
            raise ValueError("demand must be finite and non-negative")
        if not np.all(np.isfinite(self.makespan)) or np.any(self.makespan <= 0):
            raise ValueError("makespan must be finite and strictly positive")
        if not np.isfinite(self.time_per_employee) or self.time_per_employee <= 0:
            raise ValueError("time_per_employee must be finite and strictly positive")
        if self.headcount is not None and self.headcount <= 0:
            raise ValueError("headcount must be strictly positive when provided")
        if self.congestion is not None and (
            not np.all(np.isfinite(self.congestion)) or np.any(self.congestion < 0)
        ):
            raise ValueError("congestion coefficients must be finite and non-negative")
        if self.buffer_capacity is not None and (
            np.any(np.isnan(self.buffer_capacity)) or np.any(self.buffer_capacity <= 0)
        ):
            raise ValueError("buffer_capacity must be strictly positive (use inf for unbounded)")

        rho = self.spectral_radius()
        if rho > 1.0 - _SPECTRAL_TOL:
            raise ValueError(
                f"routing is unstable: spectral radius {rho:.6f} >= 1 means rework never "
                "drains. Reduce rework ratios so work eventually exits the system."
            )

    # -- derived ---------------------------------------------------------------
    def spectral_radius(self) -> float:
        """Largest absolute eigenvalue of ``P``; must be < 1 for an equilibrium to exist."""
        if self.n == 0:
            return 0.0
        return float(np.max(np.abs(np.linalg.eigvals(self.routing))))

    def is_stable(self) -> bool:
        return self.spectral_radius() <= 1.0 - _SPECTRAL_TOL

    def root_nodes(self) -> list[int]:
        """Indices of departments with no internal inflow (all-zero routing row)."""
        inflow = self.routing.sum(axis=1)
        return [i for i in range(self.n) if inflow[i] == 0.0]

    def root_names(self) -> list[str]:
        return [self.names[i] for i in self.root_nodes()]
