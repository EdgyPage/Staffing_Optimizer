"""Render a department network as a labeled block-and-arrow diagram.

A `DiagramModel` (nodes + edges, with root and rework flags) can be built from a valid
`DepartmentNetwork` (`from_network`, annotated with computed throughput) or from a raw parse
result that may be invalid (`from_parse`). It renders to:

- `to_dot`   — Graphviz DOT (the dashboard shows this via `st.graphviz_chart`, no install needed),
- `to_mermaid` — Mermaid flowchart (renders in GitHub / VS Code / mermaid.live),
- `render_image` — a PNG/SVG image file (needs the optional `viz` extra: matplotlib + networkx).

Roots are highlighted; rework edges (those that loop back) are drawn dashed and red.
"""
from __future__ import annotations

from dataclasses import dataclass

from staffing_optimizer.diagnostics import _roots_first, back_edges
from staffing_optimizer.equilibrium import throughput
from staffing_optimizer.network import DepartmentNetwork


def _num(value: float) -> str:
    value = float(value)
    return str(int(value)) if value == int(value) else f"{value:g}"


@dataclass
class NodeView:
    name: str
    sublabel: str
    is_root: bool


@dataclass
class EdgeView:
    src: str
    dst: str
    ratio: float
    is_rework: bool


@dataclass
class DiagramModel:
    title: str
    nodes: list[NodeView]
    edges: list[EdgeView]

    @classmethod
    def from_network(cls, net: DepartmentNetwork, *, annotate: bool = True, title: str | None = None) -> "DiagramModel":
        roots = set(net.root_nodes())
        lam = throughput(net) if annotate else None
        nodes = []
        for i, nm in enumerate(net.names):
            bits = [f"m={_num(net.makespan[i])}"]
            if net.demand[i]:
                bits.append(f"d={_num(net.demand[i])}")
            if lam is not None:
                bits.append(f"λ={lam[i]:.0f}")
            nodes.append(NodeView(nm, ", ".join(bits), i in roots))

        idx_edges = [(j, i) for i in range(net.n) for j in range(net.n) if net.routing[i, j] != 0.0]
        backs = back_edges(net.n, idx_edges, _roots_first(net.n, net.root_nodes()))
        edges = [
            EdgeView(net.names[j], net.names[i], float(net.routing[i, j]), (j, i) in backs)
            for (j, i) in idx_edges
        ]
        return cls(title or net.name or "network", nodes, edges)

    @classmethod
    def from_parse(cls, result, *, title: str | None = None) -> "DiagramModel":
        names = list(result.names)
        idx = {nm: k for k, nm in enumerate(names)}
        for src, dst, _ratio, _line in result.edges:        # include undefined-but-referenced nodes
            for nm in (src, dst):
                if nm not in idx:
                    idx[nm] = len(names)
                    names.append(nm)
        n = len(names)
        has_inbound = {idx[dst] for _src, dst, _ratio, _line in result.edges}
        idx_edges = [(idx[src], idx[dst]) for src, dst, _ratio, _line in result.edges]
        roots = [k for k in range(n) if k not in has_inbound]
        backs = back_edges(n, idx_edges, _roots_first(n, roots))

        nodes = []
        for k, nm in enumerate(names):
            p = result.params.get(nm, {})
            bits = [f"m={_num(p['makespan'])}" if "makespan" in p else "m=?"]
            if p.get("demand"):
                bits.append(f"d={_num(p['demand'])}")
            nodes.append(NodeView(nm, ", ".join(bits), k not in has_inbound))
        edges = [
            EdgeView(src, dst, ratio, (idx[src], idx[dst]) in backs)
            for src, dst, ratio, _line in result.edges
        ]
        return cls(title or getattr(result, "name", None) or "design", nodes, edges)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(model: DiagramModel) -> str:
    lines = [
        "digraph design {",
        "  rankdir=LR;",
        '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=10];',
    ]
    for nd in model.nodes:
        label = _esc(nd.name + (f"\n{nd.sublabel}" if nd.sublabel else ""))
        fill = "#d9f0d9" if nd.is_root else "#eef2f7"
        lines.append(f'  "{_esc(nd.name)}" [label="{label}", fillcolor="{fill}"];')
    for e in model.edges:
        style = ', style=dashed, color="#d62728", fontcolor="#d62728"' if e.is_rework else ""
        lines.append(f'  "{_esc(e.src)}" -> "{_esc(e.dst)}" [label="{_num(e.ratio)}"{style}];')
    lines.append("}")
    return "\n".join(lines)


def to_mermaid(model: DiagramModel) -> str:
    lines = ["flowchart LR"]
    ids = {nd.name: f"n{k}" for k, nd in enumerate(model.nodes)}
    for nd in model.nodes:
        text = nd.name + (f"<br/>{nd.sublabel}" if nd.sublabel else "")
        lines.append(f'  {ids[nd.name]}["{text}"]')
    for e in model.edges:
        a, b = ids.get(e.src), ids.get(e.dst)
        if a is None or b is None:
            continue
        if e.is_rework:
            lines.append(f'  {a} -. "{_num(e.ratio)}" .-> {b}')
        else:
            lines.append(f'  {a} -- "{_num(e.ratio)}" --> {b}')
    roots = [ids[nd.name] for nd in model.nodes if nd.is_root]
    if roots:
        lines.append("  classDef root fill:#d9f0d9,stroke:#2ca02c;")
        lines.append("  class " + ",".join(roots) + " root;")
    return "\n".join(lines)


def _layered_positions(model: DiagramModel, nx):
    """Left-to-right layered layout: layer = depth in the forward (rework-free) DAG."""
    forward = nx.DiGraph()
    forward.add_nodes_from(nd.name for nd in model.nodes)
    for e in model.edges:
        if not e.is_rework:
            forward.add_edge(e.src, e.dst)
    try:
        generations = list(nx.topological_generations(forward))
    except nx.NetworkXUnfeasible:
        generations = [[nd.name for nd in model.nodes]]
    pos = {}
    for layer, group in enumerate(generations):
        for k, name in enumerate(sorted(group)):
            pos[name] = (layer * 2.6, -k * 1.6)
    for k, nd in enumerate(model.nodes):
        pos.setdefault(nd.name, (0.0, -k * 1.6))
    return pos


def render_image(model: DiagramModel, out, *, dpi: int = 150, fmt: str | None = None):
    """Render the diagram to an image file or file-like object. Needs the `viz` extra."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
        from matplotlib.patches import FancyArrowPatch
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            'Rendering an image needs the "viz" extra: pip install -e ".[viz]" (matplotlib, networkx).'
        ) from exc

    pos = _layered_positions(model, nx)
    xs = [p[0] for p in pos.values()] or [0.0]
    ys = [p[1] for p in pos.values()] or [0.0]
    fig, ax = plt.subplots(figsize=(max(6.0, (max(xs) - min(xs)) + 3.0),
                                    max(3.5, (max(ys) - min(ys)) + 2.5)))
    ax.axis("off")

    for e in model.edges:
        if e.src not in pos or e.dst not in pos:
            continue
        (x0, y0), (x1, y1) = pos[e.src], pos[e.dst]
        color = "#d62728" if e.is_rework else "#555555"
        rad = 0.3 if e.is_rework else 0.0
        ax.add_patch(
            FancyArrowPatch(
                (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=14,
                connectionstyle=f"arc3,rad={rad}", color=color,
                linestyle="dashed" if e.is_rework else "solid",
                shrinkA=20, shrinkB=20, lw=1.4, zorder=1,
            )
        )
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + (0.3 if e.is_rework else 0.0)
        ax.text(mx, my, _num(e.ratio), color=color, fontsize=8, ha="center", va="center", zorder=3,
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.85))

    for nd in model.nodes:
        x, y = pos[nd.name]
        label = nd.name + (f"\n{nd.sublabel}" if nd.sublabel else "")
        ax.text(x, y, label, ha="center", va="center", fontsize=9, zorder=2,
                bbox=dict(boxstyle="round,pad=0.4", fc="#d9f0d9" if nd.is_root else "#eef2f7",
                          ec="#2c3e50", lw=1.2))

    ax.set_xlim(min(xs) - 1.6, max(xs) + 1.6)
    ax.set_ylim(min(ys) - 1.4, max(ys) + 1.4)
    ax.set_title(model.title)
    fig.savefig(out, dpi=dpi, format=fmt, bbox_inches="tight")
    plt.close(fig)
    return out
