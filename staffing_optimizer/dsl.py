"""Arrow-flow design language: parse and dump the stakeholder-facing text format.

Format::

    period_time = 480           # -> time_per_employee (T)
    headcount   = 50            # -> headcount (S)

    Receiving [makespan=2.0, demand=3800]
    Putaway   [makespan=1.5, congestion=0.02]

    Receiving -> Putaway : 1.0
    Packing   -> Picking : 0.10   # rework

`#` comments and blank lines are ignored. `parse_design` never raises on bad input — it returns
a `DesignParseResult` whose `diagnostics` describe every problem (with line numbers) and whose
`network` is built only when the design is structurally sound.

Usage::

    from staffing_optimizer.dsl import parse_design, dump_design

    result = parse_design(open("examples/warehouse_5dept.flow").read())
    result.ok          # False if any error-level diagnostics
    result.network     # a DepartmentNetwork, or None if unsound
    for d in result.diagnostics:
        print(d)       # e.g. "[ERROR] line 5: Flow references undefined department 'C'."
    print(dump_design(result.network))   # serialize a network back to .flow text
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from staffing_optimizer.diagnostics import Diagnostic, Severity, diagnose, find_cycle
from staffing_optimizer.network import DepartmentNetwork

_SETTING_ALIASES = {
    "period_time": "time_per_employee",
    "time_per_employee": "time_per_employee",
    "headcount": "headcount",
}
_DEPT_PARAMS = ("makespan", "demand", "congestion", "buffer")

_SETTING_RE = re.compile(r"^(?P<key>[A-Za-z_]+)\s*=\s*(?P<value>\S+)\s*$")
_DEPT_RE = re.compile(r"^(?P<name>.+?)\s*\[(?P<params>.*)\]\s*$")
_FLOW_RE = re.compile(r"^(?P<src>.+?)\s*->\s*(?P<dst>.+?)\s*:\s*(?P<ratio>\S+)\s*$")


def _num(value: float) -> str:
    value = float(value)
    return str(int(value)) if value == int(value) else f"{value:g}"


@dataclass
class DesignParseResult:
    network: DepartmentNetwork | None
    diagnostics: list[Diagnostic]
    names: list[str]
    params: dict[str, dict[str, float]]
    edges: list[tuple[str, str, float, int]]      # (src, dst, ratio, line)
    settings: dict[str, float] = field(default_factory=dict)
    name: str | None = None

    @property
    def ok(self) -> bool:
        return not any(d.severity == Severity.ERROR for d in self.diagnostics)


def _strip_comment(line: str) -> str:
    idx = line.find("#")
    return line if idx < 0 else line[:idx]


def _parse_params(text: str, lineno: int) -> tuple[dict[str, float], list[Diagnostic]]:
    params: dict[str, float] = {}
    errors: list[Diagnostic] = []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        if "=" not in part:
            errors.append(Diagnostic(Severity.ERROR, f"Malformed parameter '{part}' (expected key=value).", lineno))
            continue
        key, _, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if key not in _DEPT_PARAMS:
            errors.append(
                Diagnostic(Severity.ERROR, f"Unknown parameter '{key}' (allowed: {', '.join(_DEPT_PARAMS)}).", lineno)
            )
            continue
        try:
            params[key] = float(value)
        except ValueError:
            errors.append(Diagnostic(Severity.ERROR, f"Parameter '{key}' has non-numeric value '{value}'.", lineno))
    return params, errors


def parse_design(text: str, name: str | None = None) -> DesignParseResult:
    names: list[str] = []
    params: dict[str, dict[str, float]] = {}
    edges: list[tuple[str, str, float, int]] = []
    settings: dict[str, float] = {}
    diags: list[Diagnostic] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue

        setting = _SETTING_RE.match(line)
        if setting and "->" not in line and "[" not in line:
            key = setting.group("key")
            if key not in _SETTING_ALIASES:
                diags.append(Diagnostic(Severity.ERROR, f"Unknown setting '{key}'.", lineno))
                continue
            try:
                settings[_SETTING_ALIASES[key]] = float(setting.group("value"))
            except ValueError:
                diags.append(Diagnostic(Severity.ERROR, f"Setting '{key}' has non-numeric value.", lineno))
            continue

        if "->" in line:
            flow = _FLOW_RE.match(line)
            if not flow:
                diags.append(Diagnostic(Severity.ERROR, f"Could not parse flow line: '{line}'.", lineno))
                continue
            try:
                ratio = float(flow.group("ratio"))
            except ValueError:
                diags.append(Diagnostic(Severity.ERROR, f"Invalid ratio in flow: '{line}'.", lineno))
                continue
            edges.append((flow.group("src").strip(), flow.group("dst").strip(), ratio, lineno))
            continue

        dept = _DEPT_RE.match(line)
        if dept:
            nm = dept.group("name").strip()
            if nm in params:
                diags.append(Diagnostic(Severity.ERROR, f"Department '{nm}' is defined more than once.", lineno))
                continue
            parsed, perrs = _parse_params(dept.group("params"), lineno)
            diags.extend(perrs)
            if "makespan" not in parsed:
                diags.append(Diagnostic(Severity.ERROR, f"Department '{nm}' is missing required 'makespan'.", lineno))
            names.append(nm)
            params[nm] = parsed
            continue

        diags.append(Diagnostic(Severity.ERROR, f"Could not parse line: '{line}'.", lineno))

    # flows referencing undefined departments
    seen: dict[str, int] = {}
    for src, dst, _ratio, lineno in edges:
        for endpoint in (src, dst):
            if endpoint not in params and endpoint not in seen:
                seen[endpoint] = lineno
    for endpoint, lineno in seen.items():
        diags.append(Diagnostic(Severity.ERROR, f"Flow references undefined department '{endpoint}'.", lineno))

    network = _build_network(names, params, edges, settings, name, diags)
    if network is not None:
        diags.extend(diagnose(network))

    diags.sort(key=lambda d: (d.line is None, d.line or 0))
    return DesignParseResult(network, diags, names, params, edges, settings, name)


def _build_network(names, params, edges, settings, name, diags) -> DepartmentNetwork | None:
    if not names:
        diags.append(Diagnostic(Severity.ERROR, "No departments defined."))
        return None
    if any(d.severity == Severity.ERROR for d in diags):
        return None  # incomplete/invalid; leave the diagram to render from the raw parse

    idx = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    makespan = np.array([params[nm]["makespan"] for nm in names])
    demand = np.array([params[nm].get("demand", 0.0) for nm in names])
    congestion = np.array([params[nm].get("congestion", 0.0) for nm in names])
    raw_buffers = [params[nm].get("buffer") for nm in names]
    buffer_capacity = (
        np.array([b if b is not None else np.inf for b in raw_buffers])
        if any(b is not None for b in raw_buffers)
        else None
    )
    routing = np.zeros((n, n))
    for src, dst, ratio, _lineno in edges:
        routing[idx[dst], idx[src]] = ratio

    try:
        return DepartmentNetwork(
            names=names, routing=routing, demand=demand, makespan=makespan,
            time_per_employee=settings.get("time_per_employee", 1.0),
            headcount=settings.get("headcount"), congestion=congestion,
            buffer_capacity=buffer_capacity, name=name,
        )
    except ValueError as exc:
        message = str(exc)
        if "spectral radius" in message:
            cycle = find_cycle(n, [(idx[s], idx[d]) for s, d, _r, _ln in edges])
            if cycle:
                loop = " -> ".join(names[i] for i in [*cycle, cycle[0]])
                message += f" Offending loop: {loop}."
        diags.append(Diagnostic(Severity.ERROR, message))
        return None


def dump_design(net: DepartmentNetwork) -> str:
    """Serialize a network back to the arrow-flow format (round-trips through `parse_design`)."""
    from staffing_optimizer.diagnostics import rework_edges  # local import avoids cycle at import time

    lines = [f"period_time = {_num(net.time_per_employee)}"]
    if net.headcount is not None:
        lines.append(f"headcount = {_num(net.headcount)}")
    lines.append("")

    for i, nm in enumerate(net.names):
        parts = [f"makespan={_num(net.makespan[i])}"]
        if net.demand[i] != 0:
            parts.append(f"demand={_num(net.demand[i])}")
        if net.congestion is not None and net.congestion[i] != 0:
            parts.append(f"congestion={_num(net.congestion[i])}")
        if net.buffer_capacity is not None and np.isfinite(net.buffer_capacity[i]):
            parts.append(f"buffer={_num(net.buffer_capacity[i])}")
        lines.append(f"{nm} [{', '.join(parts)}]")
    lines.append("")

    rework = set(rework_edges(net))
    for j in range(net.n):          # source
        for i in range(net.n):      # destination
            if net.routing[i, j] != 0.0:
                tag = "   # rework" if (j, i) in rework else ""
                lines.append(f"{net.names[j]} -> {net.names[i]} : {_num(net.routing[i, j])}{tag}")
    return "\n".join(lines) + "\n"
