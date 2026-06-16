"""Time-stepped backlog simulation with exponential congestion.

The static engine answers "what staffing keeps the system balanced?".  This simulates what
happens *over time* for a given staffing vector, with the headline behavior the project calls
for: as a department's backlog ``B`` grows, its effective makespan grows exponentially —

    m_eff_i = m_i * exp(beta_i * B_i)

so processing capacity ``s_i * T / m_eff_i`` collapses and the backlog runs away.  Departments
with ``beta_i = 0`` (the "few exceptions", e.g. automated lines) never congest.

Each step routes the previous step's completions downstream (an explicit one-step handoff),
which is the Jacobi iteration for ``lambda = (I - P)^-1 d``.  So with ample staffing the
simulation converges to the static equilibrium throughput ``lambda`` and the backlog stays
bounded — the dynamic and static models agree.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from staffing_optimizer.network import DepartmentNetwork

# Once backlog drives the congestion exponent past this, capacity is already negligible; we cap
# it so effective makespan stays a (very large) finite number rather than overflowing to inf.
_MAX_CONGESTION_EXPONENT = 80.0


def _effective_makespan(base_m: np.ndarray, beta: np.ndarray, backlog: np.ndarray) -> np.ndarray:
    return base_m * np.exp(np.minimum(beta * backlog, _MAX_CONGESTION_EXPONENT))


@dataclass
class SimulationResult:
    times: np.ndarray              # (steps + 1,) period marks
    backlog: np.ndarray            # (steps + 1, n) units waiting at each department
    arrivals: np.ndarray           # (steps, n) arrival rate (units/period) per interval
    completions: np.ndarray        # (steps, n) completion rate (units/period) per interval
    effective_makespan: np.ndarray  # (steps + 1, n) m * exp(beta * B)
    names: list[str]
    dt: float

    @property
    def final_backlog(self) -> np.ndarray:
        return self.backlog[-1]

    @property
    def final_completions(self) -> np.ndarray:
        return self.completions[-1]


def simulate(
    net: DepartmentNetwork,
    staffing,
    *,
    dt: float = 0.05,
    horizon: float = 50.0,
    initial_backlog=None,
    backpressure_band: float = 0.2,
) -> SimulationResult:
    """Simulate backlog evolution for a fixed ``staffing`` vector (employees per department).

    ``dt`` and ``horizon`` are in periods (e.g. shifts).  Returns time series of backlog,
    arrival/completion rates and effective makespan.

    If the network sets ``buffer_capacity`` (max backlog per department), **backpressure** is
    applied: as a department's backlog enters the top ``backpressure_band`` fraction of its
    buffer, its upstream feeders are throttled, so backlog propagates upstream toward the root
    instead of piling up only at the bottleneck. Departments with an unbounded (inf) buffer never
    push back. The throttle only engages near-full, so adequate staffing still converges to ``λ``.
    """
    n = net.n
    staffing = np.asarray(staffing, dtype=float)
    if staffing.shape != (n,):
        raise ValueError(f"staffing must have length {n}, got {staffing.shape}")
    if dt <= 0 or horizon <= 0:
        raise ValueError("dt and horizon must be strictly positive")
    if not 0 < backpressure_band <= 1:
        raise ValueError("backpressure_band must be in (0, 1]")

    beta = net.congestion if net.congestion is not None else np.zeros(n)
    base_m = net.makespan
    cap_const = staffing * net.time_per_employee  # capacity numerator: s * T (units of work-time)
    routing = net.routing
    demand = net.demand
    steps = max(1, round(horizon / dt))

    # backpressure setup: which downstream destination each department feeds, and buffer bands
    buffer = net.buffer_capacity
    backpressure = buffer is not None and bool(np.any(np.isfinite(buffer)))
    if buffer is None:
        buffer = np.full(n, np.inf)
    finite_buffer = np.isfinite(buffer)
    band = np.where(finite_buffer, backpressure_band * buffer, np.inf)
    feeds = routing != 0.0  # feeds[r, i] is True when i sends work to r

    backlog = np.zeros(n) if initial_backlog is None else np.asarray(initial_backlog, float).copy()
    prev_completions = np.zeros(n)

    times = np.zeros(steps + 1)
    backlog_hist = np.zeros((steps + 1, n))
    meff_hist = np.zeros((steps + 1, n))
    arrivals_hist = np.zeros((steps, n))
    completions_hist = np.zeros((steps, n))

    backlog_hist[0] = backlog
    meff_hist[0] = _effective_makespan(base_m, beta, backlog)

    for k in range(steps):
        m_eff = _effective_makespan(base_m, beta, backlog)
        capacity = cap_const / m_eff                       # units/period a department can clear
        if backpressure:
            # room[r] in [0, 1]: 1 with space to spare, 0 when buffer r is full.
            room = np.ones(n)
            room[finite_buffer] = np.clip(
                (buffer[finite_buffer] - backlog[finite_buffer]) / band[finite_buffer], 0.0, 1.0
            )
            # a department's throttle is set by its most-constrained downstream destination.
            throttle = np.where(feeds, room[:, None], 1.0).min(axis=0)
            capacity = capacity * throttle
        arrivals = demand + routing @ prev_completions      # explicit downstream handoff
        completions = np.minimum(capacity, backlog / dt + arrivals)
        completions = np.maximum(completions, 0.0)
        backlog = np.maximum(0.0, backlog + (arrivals - completions) * dt)
        prev_completions = completions

        times[k + 1] = (k + 1) * dt
        backlog_hist[k + 1] = backlog
        meff_hist[k + 1] = _effective_makespan(base_m, beta, backlog)
        arrivals_hist[k] = arrivals
        completions_hist[k] = completions

    return SimulationResult(
        times=times,
        backlog=backlog_hist,
        arrivals=arrivals_hist,
        completions=completions_hist,
        effective_makespan=meff_hist,
        names=list(net.names),
        dt=dt,
    )


def backlog_slope(result: SimulationResult, window: float = 0.2) -> np.ndarray:
    """Average dB/dt over the final ``window`` fraction of the run (units/period)."""
    steps = len(result.times) - 1
    k = max(1, int(window * steps))
    span = result.times[-1] - result.times[-1 - k]
    if span <= 0:
        return np.zeros(result.backlog.shape[1])
    return (result.backlog[-1] - result.backlog[-1 - k]) / span


def diverging_departments(result: SimulationResult, rel_tol: float = 0.01) -> list[int]:
    """Indices of departments whose backlog is still growing at the end of the run.

    A department counts as diverging when its tail backlog slope exceeds ``rel_tol`` times
    its arrival rate — i.e. it is falling behind rather than settling.
    """
    slope = backlog_slope(result)
    reference = np.maximum(1.0, result.arrivals[-1])
    return [i for i in range(len(slope)) if slope[i] > rel_tol * reference[i]]
