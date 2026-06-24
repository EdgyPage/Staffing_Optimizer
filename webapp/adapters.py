"""Integration layer between the JSON *design document* and the engine.

The web app's canonical object is a plain "design document" (see the schema below) — JSON the
front-end builds and the store persists. Everything the engine needs is derived here, and
nothing in the engine is re-implemented; this module only translates.

Design document::

    {
      "name": str, "created_at": ISO-str|null, "valid": bool|null,
      "settings": {"time_per_employee": float, "headcount": float|null},
      "departments": [{"name", "makespan", "demand", "congestion", "buffer"|null, "x"|null, "y"|null}],
      "flows": [{"from", "to", "ratio"}],
    }
"""
from __future__ import annotations

import numpy as np

from staffing_optimizer import equilibrium as eq
from staffing_optimizer import gaps as gp
from staffing_optimizer.diagnostics import (
    Diagnostic,
    Severity,
    _roots_first,
    back_edges,
    diagnose,
    find_cycle,
    reachable_from_edges,
)
from staffing_optimizer.dsl import dump_design, parse_design
from staffing_optimizer.dynamics import SimulationResult
from staffing_optimizer.io_scenario import loads as load_yaml
from staffing_optimizer.network import DepartmentNetwork

_MAX_FRAMES = 600  # cap simulation frames returned to the client for smooth playback


# --------------------------------------------------------------------------- doc <-> network
def doc_to_network(doc: dict) -> DepartmentNetwork:
    depts = doc["departments"]
    names = [d["name"] for d in depts]
    idx = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    makespan = np.array([float(d["makespan"]) for d in depts])
    demand = np.array([float(d.get("demand") or 0.0) for d in depts])
    congestion = np.array([float(d.get("congestion") or 0.0) for d in depts])
    buffers = [d.get("buffer") for d in depts]
    buffer_capacity = (
        np.array([float(b) if b is not None else np.inf for b in buffers])
        if any(b is not None for b in buffers)
        else None
    )
    routing = np.zeros((n, n))
    for flow in doc.get("flows", []):
        routing[idx[flow["to"]], idx[flow["from"]]] = float(flow["ratio"])
    settings = doc.get("settings") or {}
    headcount = settings.get("headcount")
    return DepartmentNetwork(
        names=names,
        routing=routing,
        demand=demand,
        makespan=makespan,
        time_per_employee=float(settings.get("time_per_employee", 1.0)),
        headcount=None if headcount in (None, "") else float(headcount),
        congestion=congestion,
        buffer_capacity=buffer_capacity,
        name=doc.get("name"),
    )


def network_to_doc(net: DepartmentNetwork, *, name: str | None = None, positions=None,
                   valid: bool | None = None) -> dict:
    positions = positions or {}
    departments = []
    for i, nm in enumerate(net.names):
        pos = positions.get(nm, {})
        buffer = None
        if net.buffer_capacity is not None and np.isfinite(net.buffer_capacity[i]):
            buffer = float(net.buffer_capacity[i])
        departments.append({
            "name": nm,
            "makespan": float(net.makespan[i]),
            "demand": float(net.demand[i]),
            "congestion": float(net.congestion[i]) if net.congestion is not None else 0.0,
            "buffer": buffer,
            "x": pos.get("x"),
            "y": pos.get("y"),
        })
    flows = []
    for j in range(net.n):          # source
        for i in range(net.n):      # destination
            if net.routing[i, j] != 0.0:
                flows.append({"from": net.names[j], "to": net.names[i], "ratio": float(net.routing[i, j])})
    return {
        "name": name or net.name or "design",
        "created_at": None,
        "valid": valid,
        "settings": {
            "time_per_employee": float(net.time_per_employee),
            "headcount": float(net.headcount) if net.headcount is not None else None,
        },
        "departments": departments,
        "flows": flows,
    }


# --------------------------------------------------------------------------- validation
def validate_doc(doc: dict) -> tuple[DepartmentNetwork | None, list[Diagnostic], bool]:
    """Return (network or None, diagnostics, ok). Never raises."""
    diags: list[Diagnostic] = []
    depts = doc.get("departments") or []
    names = [d.get("name") for d in depts]

    if not depts:
        diags.append(Diagnostic(Severity.ERROR, "No departments defined."))
    seen: set[str] = set()
    for d in depts:
        nm = d.get("name")
        if not nm:
            diags.append(Diagnostic(Severity.ERROR, "A department is missing a name."))
        elif nm in seen:
            diags.append(Diagnostic(Severity.ERROR, f"Department '{nm}' is defined more than once."))
        seen.add(nm)
        if d.get("makespan") in (None, ""):
            diags.append(Diagnostic(Severity.ERROR, f"Department '{nm}' is missing makespan."))
    nameset = set(names)
    for flow in doc.get("flows") or []:
        for endpoint in (flow.get("from"), flow.get("to")):
            if endpoint not in nameset:
                diags.append(Diagnostic(Severity.ERROR, f"Flow references unknown department '{endpoint}'."))

    net = None
    if not any(d.severity is Severity.ERROR for d in diags):
        try:
            net = doc_to_network(doc)
        except (ValueError, KeyError) as exc:
            message = str(exc)
            if "spectral radius" in message:
                message = _name_cycle(doc, message)
            diags.append(Diagnostic(Severity.ERROR, message))
            net = None
    if net is not None:
        diags.extend(diagnose(net))

    ok = not any(d.severity is Severity.ERROR for d in diags)
    return net, diags, ok


def _name_cycle(doc: dict, message: str) -> str:
    names = [d.get("name") for d in doc.get("departments", [])]
    idx = {nm: i for i, nm in enumerate(names)}
    edges = [(idx[f["from"]], idx[f["to"]]) for f in doc.get("flows", [])
             if f.get("from") in idx and f.get("to") in idx]
    cycle = find_cycle(len(names), edges)
    if cycle:
        loop = " -> ".join(names[i] for i in [*cycle, cycle[0]])
        return f"{message} Offending loop: {loop}."
    return message


def diagnostics_json(diags: list[Diagnostic]) -> list[dict]:
    return [{"severity": d.severity.value, "message": d.message, "line": d.line} for d in diags]


# --------------------------------------------------------------------------- graph for the canvas
def graph_json(doc: dict) -> dict:
    """Nodes + edges with is_root / is_rework for the Cytoscape canvas (works even if invalid)."""
    depts = doc.get("departments") or []
    names = [d.get("name") for d in depts]
    idx = {nm: i for i, nm in enumerate(names) if nm}
    n = len(names)

    edges_idx = []
    has_inbound: set[int] = set()
    for flow in doc.get("flows") or []:
        src, dst = flow.get("from"), flow.get("to")
        if src in idx and dst in idx:
            edges_idx.append((idx[src], idx[dst]))
            has_inbound.add(idx[dst])
    roots = [i for i in range(n) if i not in has_inbound]
    roots_set = set(roots)
    backs = back_edges(n, edges_idx, _roots_first(n, roots))

    # "gets work" = reachable from any department that has demand (the true entry points),
    # plus each department's total outflow — both drive the live builder status.
    reach = reachable_from_edges(n, edges_idx)
    sources = [i for i in range(n) if float(depts[i].get("demand") or 0) > 0]
    gets_work = set(sources)
    for s in sources:
        gets_work.update(int(k) for k in reach[s].nonzero()[0])
    has_sources = bool(sources)
    outflow: dict[str, float] = {}
    for flow in doc.get("flows") or []:
        src = flow.get("from")
        if src in idx:
            outflow[src] = outflow.get(src, 0.0) + float(flow.get("ratio") or 0.0)

    nodes = []
    for i, d in enumerate(depts):
        name = d.get("name")
        demand = float(d.get("demand") or 0)
        of = outflow.get(name, 0.0)
        is_root = i in roots_set
        is_reachable = (i in gets_work) if has_sources else True
        notes, status = [], "ok"
        if is_root:
            notes.append("root")
            if demand == 0:
                notes.append("no demand")
                status = "warn"
        if has_sources and i not in gets_work:
            notes.append("no inbound work")
            status = "warn"
        if i not in has_inbound and of == 0 and demand == 0:
            notes.append("isolated")
            status = "warn"
        if of > 1.0 + 1e-9:
            notes.append(f"fan-out {round(of * 100)}%")
        nodes.append({
            "id": name,
            "makespan": d.get("makespan"),
            "demand": demand,
            "congestion": d.get("congestion") or 0,
            "buffer": d.get("buffer"),
            "x": d.get("x"),
            "y": d.get("y"),
            "is_root": is_root,
            "reachable": is_reachable,
            "outflow": of,
            "status": status,
            "notes": notes,
        })
    edges = []
    for flow in doc.get("flows") or []:
        src, dst = flow.get("from"), flow.get("to")
        is_rework = src in idx and dst in idx and (idx[src], idx[dst]) in backs
        edges.append({"from": src, "to": dst, "ratio": flow.get("ratio"), "is_rework": is_rework})
    return {"nodes": nodes, "edges": edges, "roots": [names[i] for i in roots]}


# --------------------------------------------------------------------------- analysis
def analysis_json(net: DepartmentNetwork) -> dict:
    lam = eq.throughput(net)
    required = eq.staffing_requirement(net)
    split = eq.staffing_split(net)
    suggested = gp.suggested_allocation(net, net.headcount) if net.headcount else required
    feas = gp.feasibility(net, net.headcount)
    rows = gp.gap_report(net, suggested)
    basis = eq.basis_matrix(net)
    roots = net.root_nodes()
    return {
        "names": list(net.names),
        "throughput": [float(x) for x in lam],
        "required_fte": [float(x) for x in required],
        "split": [float(x) for x in split],
        "suggested": [float(x) for x in suggested],
        "feasibility": {
            "required_fte": feas["required_fte"],
            "headcount": feas["headcount"],
            "utilization": feas["utilization"],
            "feasible": feas["feasible"],
            "shortfall_fte": feas["shortfall_fte"],
        },
        "gaps": [
            {"name": r.name, "required": r.required_fte, "actual": r.actual_fte,
             "gap_fte": r.gap_fte, "status": r.status}
            for r in rows
        ],
        "basis": {
            "roots": [net.names[j] for j in roots],
            "matrix": [[float(basis[i, j]) for j in roots] for i in range(net.n)],
        },
    }


# --------------------------------------------------------------------------- simulation series
def result_json(result: SimulationResult) -> dict:
    from staffing_optimizer.dynamics import diverging_departments

    steps = len(result.times)
    keep = _frame_indices(steps)
    diverging = [result.names[i] for i in diverging_departments(result)]
    return {
        "names": list(result.names),
        "times": [float(result.times[k]) for k in keep],
        "backlog": [[float(v) for v in result.backlog[k]] for k in keep],
        "effective_makespan": [[float(v) for v in result.effective_makespan[k]] for k in keep],
        "diverging": diverging,
    }


def _frame_indices(steps: int) -> list[int]:
    if steps <= _MAX_FRAMES:
        return list(range(steps))
    return sorted({round(i * (steps - 1) / (_MAX_FRAMES - 1)) for i in range(_MAX_FRAMES)})


# --------------------------------------------------------------------------- portability
def doc_to_flow(doc: dict) -> str:
    return dump_design(doc_to_network(doc))


def flow_to_doc(text: str, name: str | None = None) -> dict:
    result = parse_design(text, name=name)
    if result.network is None:
        raise ValueError("; ".join(str(d) for d in result.diagnostics if d.severity is Severity.ERROR)
                         or "design is not valid")
    return network_to_doc(result.network, name=name)


def yaml_to_doc(text: str, name: str | None = None) -> dict:
    return network_to_doc(load_yaml(text), name=name)


def doc_to_yaml(doc: dict) -> str:
    import yaml

    net = doc_to_network(doc)
    out: dict = {"name": net.name, "time_per_employee": float(net.time_per_employee)}
    if net.headcount is not None:
        out["headcount"] = float(net.headcount)
    departments = []
    for i, nm in enumerate(net.names):
        entry = {"name": nm, "makespan": float(net.makespan[i]), "demand": float(net.demand[i])}
        if net.congestion is not None and net.congestion[i]:
            entry["congestion"] = float(net.congestion[i])
        if net.buffer_capacity is not None and np.isfinite(net.buffer_capacity[i]):
            entry["buffer"] = float(net.buffer_capacity[i])
        departments.append(entry)
    routes = [
        {"from": net.names[j], "to": net.names[i], "ratio": float(net.routing[i, j])}
        for j in range(net.n) for i in range(net.n) if net.routing[i, j] != 0.0
    ]
    out["departments"] = departments
    out["routes"] = routes
    return yaml.safe_dump(out, sort_keys=False)
