"""Load and save scenarios.

The primary format is YAML: a node table (``departments``) plus a routing edge list
(``routes``), both human-editable.  A light CSV loader (separate nodes + routes files) is
also provided for spreadsheet workflows.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import yaml

from staffing_optimizer.network import DepartmentNetwork


def _from_dict(data: dict) -> DepartmentNetwork:
    depts = data["departments"]
    names = [d["name"] for d in depts]
    idx = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    makespan = np.array([float(d["makespan"]) for d in depts])
    demand = np.array([float(d.get("demand", 0.0)) for d in depts])
    congestion = np.array([float(d.get("congestion", 0.0)) for d in depts])
    routing = np.zeros((n, n))
    for route in data.get("routes", []):
        i, j = idx[route["to"]], idx[route["from"]]
        routing[i, j] = float(route["ratio"])
    headcount = data.get("headcount")
    return DepartmentNetwork(
        names=names,
        routing=routing,
        demand=demand,
        makespan=makespan,
        time_per_employee=float(data.get("time_per_employee", 1.0)),
        headcount=None if headcount is None else float(headcount),
        congestion=congestion,
        name=data.get("name"),
    )


def loads(text: str) -> DepartmentNetwork:
    """Parse a scenario from a YAML string (e.g. an uploaded file's contents)."""
    return _from_dict(yaml.safe_load(text))


def load_scenario(path) -> DepartmentNetwork:
    """Load a scenario from a YAML file."""
    return _from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def save_scenario(net: DepartmentNetwork, path) -> None:
    """Write a network back out as a YAML scenario (node table + routing edge list)."""
    depts = []
    for i, nm in enumerate(net.names):
        entry = {"name": nm, "makespan": float(net.makespan[i]), "demand": float(net.demand[i])}
        if net.congestion is not None:
            entry["congestion"] = float(net.congestion[i])
        depts.append(entry)
    routes = []
    for j in range(net.n):          # j = source department
        for i in range(net.n):      # i = destination department
            if net.routing[i, j] != 0.0:
                routes.append(
                    {"from": net.names[j], "to": net.names[i], "ratio": float(net.routing[i, j])}
                )
    data: dict = {"name": net.name, "time_per_employee": float(net.time_per_employee)}
    if net.headcount is not None:
        data["headcount"] = float(net.headcount)
    data["departments"] = depts
    data["routes"] = routes
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def load_scenario_csv(
    nodes_path,
    routes_path,
    *,
    name: str | None = None,
    time_per_employee: float = 1.0,
    headcount: float | None = None,
) -> DepartmentNetwork:
    """Load a scenario from two CSV files.

    ``nodes_path`` columns: ``name, makespan, demand[, congestion]``.
    ``routes_path`` columns: ``from, to, ratio``.
    """
    with open(nodes_path, newline="", encoding="utf-8") as fh:
        nodes = list(csv.DictReader(fh))
    names = [r["name"] for r in nodes]
    idx = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    makespan = np.array([float(r["makespan"]) for r in nodes])
    demand = np.array([float(r.get("demand") or 0.0) for r in nodes])
    congestion = np.array([float(r.get("congestion") or 0.0) for r in nodes])
    routing = np.zeros((n, n))
    with open(routes_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            routing[idx[r["to"]], idx[r["from"]]] = float(r["ratio"])
    return DepartmentNetwork(
        names=names,
        routing=routing,
        demand=demand,
        makespan=makespan,
        time_per_employee=time_per_employee,
        headcount=headcount,
        congestion=congestion,
        name=name,
    )
