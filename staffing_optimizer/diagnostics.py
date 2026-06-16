"""Mathematical-soundness diagnostics for a department network.

`diagnose(net)` runs on an already-constructed (and therefore structurally valid) network and
returns a list of `Diagnostic`s — warnings and info, since hard errors (non-positive makespan,
negative ratios, unstable rework) are caught by `DepartmentNetwork.validate()` at construction
time and surfaced by the parser in `dsl.py`.

Also exposes pure-Python graph helpers (`reachable_from_edges`, `reachability`, `rework_edges`,
`unreachable_departments`, `find_cycle`) used by both the parser and the diagram renderer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from staffing_optimizer.equilibrium import staffing_requirement
from staffing_optimizer.gaps import feasibility
from staffing_optimizer.network import DepartmentNetwork

_FANOUT_TOL = 1e-9


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    severity: Severity
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"[{self.severity.value.upper()}] {where}{self.message}"


# --------------------------------------------------------------------------- graph helpers
def reachable_from_edges(n: int, edges) -> np.ndarray:
    """Boolean (n, n) matrix; ``R[a, b]`` is True if b is reachable from a via one or more hops.

    ``edges`` is an iterable of ``(src, dst)`` index pairs (work flows src -> dst).
    """
    adjacency: list[list[int]] = [[] for _ in range(n)]
    for src, dst in edges:
        adjacency[src].append(dst)
    reach = np.zeros((n, n), dtype=bool)
    for start in range(n):
        stack = list(adjacency[start])
        while stack:
            node = stack.pop()
            if not reach[start, node]:
                reach[start, node] = True
                stack.extend(adjacency[node])
    return reach


def _edge_indices(net: DepartmentNetwork) -> list[tuple[int, int]]:
    # routing[i, j] = fraction of j routed to i, so work flows j -> i.
    return [(j, i) for i in range(net.n) for j in range(net.n) if net.routing[i, j] != 0.0]


def reachability(net: DepartmentNetwork) -> np.ndarray:
    return reachable_from_edges(net.n, _edge_indices(net))


def back_edges(n: int, edges, order=None) -> set[tuple[int, int]]:
    """DFS back-edges — the edges that loop back against the forward flow (i.e. rework).

    DFS visits nodes in ``order`` (roots first, so "forward" aligns with flow from the roots).
    In a 2-cycle ``A -> B`` / ``B -> A`` discovered from A, only ``B -> A`` is a back-edge, which
    is what reachability alone gets wrong.
    """
    adjacency: list[list[int]] = [[] for _ in range(n)]
    for src, dst in edges:
        adjacency[src].append(dst)
    white, gray, black = 0, 1, 2
    color = [white] * n
    backs: set[tuple[int, int]] = set()
    for start in (range(n) if order is None else order):
        if color[start] != white:
            continue
        color[start] = gray
        stack = [(start, iter(adjacency[start]))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color[nxt] == white:
                    color[nxt] = gray
                    stack.append((nxt, iter(adjacency[nxt])))
                    advanced = True
                    break
                if color[nxt] == gray:           # edge into an ancestor on the stack
                    backs.add((node, nxt))
            if not advanced:
                color[node] = black
                stack.pop()
    return backs


def _roots_first(n: int, roots) -> list[int]:
    roots = list(roots)
    return roots + [i for i in range(n) if i not in set(roots)]


def rework_edges(net: DepartmentNetwork) -> list[tuple[int, int]]:
    """Edges ``(src, dst)`` that loop back against the forward flow from the roots."""
    order = _roots_first(net.n, net.root_nodes())
    return sorted(back_edges(net.n, _edge_indices(net), order))


def unreachable_departments(net: DepartmentNetwork) -> list[int]:
    """Departments that are neither roots nor reachable from any root."""
    roots = net.root_nodes()
    if not roots:
        return []
    reach = reachability(net)
    reachable = set(roots)
    for r in roots:
        reachable.update(np.nonzero(reach[r])[0].tolist())
    return [i for i in range(net.n) if i not in reachable]


def find_cycle(n: int, edges) -> list[int] | None:
    """Return one cycle as a list of node indices (DFS), or None if the graph is acyclic."""
    adjacency: list[list[int]] = [[] for _ in range(n)]
    for src, dst in edges:
        adjacency[src].append(dst)
    white, gray, black = 0, 1, 2
    color = [white] * n
    parent: dict[int, int] = {}

    def visit(start: int) -> list[int] | None:
        stack = [(start, iter(adjacency[start]))]
        color[start] = gray
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color[nxt] == white:
                    color[nxt] = gray
                    parent[nxt] = node
                    stack.append((nxt, iter(adjacency[nxt])))
                    advanced = True
                    break
                if color[nxt] == gray:  # back edge node -> nxt closes a cycle
                    cycle = [node]
                    cur = node
                    while cur != nxt:
                        cur = parent[cur]
                        cycle.append(cur)
                    cycle.reverse()
                    return cycle
            if not advanced:
                color[node] = black
                stack.pop()
        return None

    for s in range(n):
        if color[s] == white:
            found = visit(s)
            if found:
                return found
    return None


# --------------------------------------------------------------------------- model diagnostics
def diagnose(net: DepartmentNetwork) -> list[Diagnostic]:
    """Warnings and info for a constructed (valid) network."""
    out: list[Diagnostic] = []
    n = net.n
    roots = net.root_nodes()

    if not roots:
        out.append(
            Diagnostic(
                Severity.WARNING,
                "No root department: every department receives rework, so there is no external "
                "entry point for demand. One department should have no inbound flow.",
            )
        )
    for i in roots:
        if net.demand[i] == 0:
            out.append(Diagnostic(Severity.WARNING, f"Root '{net.names[i]}' has no demand — it will sit idle."))
    for i in range(n):
        if net.demand[i] > 0 and i not in roots:
            out.append(
                Diagnostic(
                    Severity.WARNING,
                    f"'{net.names[i]}' has demand but also receives internal rework (not a root); "
                    "external demand usually enters at a root.",
                )
            )
    for i in unreachable_departments(net):
        out.append(
            Diagnostic(Severity.WARNING, f"'{net.names[i]}' is unreachable from any root — it receives no work.")
        )

    inflow = net.routing.sum(axis=1)
    outflow = net.routing.sum(axis=0)
    for i in range(n):
        if inflow[i] == 0 and outflow[i] == 0 and net.demand[i] == 0:
            out.append(Diagnostic(Severity.WARNING, f"'{net.names[i]}' is isolated (no flow in or out, no demand)."))
    for j in range(n):
        if outflow[j] > 1.0 + _FANOUT_TOL:
            out.append(
                Diagnostic(
                    Severity.INFO,
                    f"'{net.names[j]}' sends out {outflow[j]:.2f}x its work (fan-out / work multiplication).",
                )
            )

    required = float(staffing_requirement(net).sum())
    if net.headcount:
        feas = feasibility(net, net.headcount)
        verdict = "feasible" if feas["feasible"] else f"INFEASIBLE (short {feas['shortfall_fte']:.1f} FTE)"
        out.append(
            Diagnostic(
                Severity.INFO,
                f"Requires {required:.1f} FTE vs headcount {net.headcount:g} -> "
                f"utilization {100 * feas['utilization']:.0f}% -> {verdict}.",
            )
        )
    else:
        out.append(Diagnostic(Severity.INFO, f"Requires {required:.1f} FTE (no headcount set)."))
    return out
