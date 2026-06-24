"""Streamlit dashboard for the warehouse staffing equilibrium optimizer.

.. deprecated::
    Superseded by the FastAPI web app in ``webapp/`` (run ``python -m webapp``), which adds a
    visual builder, saved/transferable designs, and interactive time-step simulation. This
    dashboard is kept for reference but is no longer the primary front end.

Edit departments, routing ratios, demand and headcount, and explore three views live:
equilibrium staffing & gaps, the time-stepped backlog dynamics, and SKU-level makespan.

Run with::

    streamlit run app/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from staffing_optimizer import diagram as dgm  # noqa: E402
from staffing_optimizer import dsl  # noqa: E402
from staffing_optimizer import dynamics as dyn  # noqa: E402
from staffing_optimizer import equilibrium as eq  # noqa: E402
from staffing_optimizer import gaps as gp  # noqa: E402
from staffing_optimizer import io_scenario  # noqa: E402
from staffing_optimizer import skus as sku  # noqa: E402
from staffing_optimizer.diagnostics import Severity  # noqa: E402
from staffing_optimizer.network import DepartmentNetwork  # noqa: E402

EXAMPLES = ROOT / "examples"


# --------------------------------------------------------------------------- helpers
def net_to_frames(net: DepartmentNetwork) -> tuple[pd.DataFrame, pd.DataFrame]:
    buffer = net.buffer_capacity
    depts = pd.DataFrame(
        {
            "department": net.names,
            "makespan": net.makespan,
            "demand": net.demand,
            "congestion": net.congestion if net.congestion is not None else np.zeros(net.n),
            "buffer": [
                np.nan if buffer is None or not np.isfinite(buffer[i]) else float(buffer[i])
                for i in range(net.n)
            ],
        }
    )
    rows = []
    for j in range(net.n):          # j = source
        for i in range(net.n):      # i = destination
            if net.routing[i, j] != 0.0:
                rows.append(
                    {"from": net.names[j], "to": net.names[i], "ratio": float(net.routing[i, j])}
                )
    routes = pd.DataFrame(rows, columns=["from", "to", "ratio"])
    return depts, routes


def frames_to_net(depts: pd.DataFrame, routes: pd.DataFrame, t: float, s: float) -> DepartmentNetwork:
    names, makespan, demand, congestion, buffers = [], [], [], [], []
    for _, row in depts.iterrows():
        nm = str(row.get("department", "") or "").strip()
        mk = row.get("makespan")
        if not nm or nm.lower() == "nan" or pd.isna(mk):
            continue  # skip blank / half-typed rows
        names.append(nm)
        makespan.append(float(mk))
        d = row.get("demand", 0.0)
        demand.append(float(d) if pd.notna(d) else 0.0)
        c = row.get("congestion", 0.0)
        congestion.append(float(c) if pd.notna(c) else 0.0)
        b = row.get("buffer")
        buffers.append(float(b) if pd.notna(b) else np.inf)

    idx = {nm: i for i, nm in enumerate(names)}
    routing = np.zeros((len(names), len(names)))
    for _, r in routes.iterrows():
        frm = str(r.get("from", "") or "").strip()
        to = str(r.get("to", "") or "").strip()
        ratio = r.get("ratio")
        if frm in idx and to in idx and pd.notna(ratio):
            routing[idx[to], idx[frm]] = float(ratio)

    buffer_capacity = np.array(buffers) if any(np.isfinite(x) for x in buffers) else None
    return DepartmentNetwork(
        names=names,
        routing=routing,
        demand=np.array(demand),
        makespan=np.array(makespan),
        time_per_employee=t,
        headcount=s,
        congestion=np.array(congestion),
        buffer_capacity=buffer_capacity,
    )


def load_into_state(net: DepartmentNetwork) -> None:
    depts, routes = net_to_frames(net)
    st.session_state.depts = depts
    st.session_state.routes = routes
    st.session_state.t = float(net.time_per_employee)
    if net.headcount:
        st.session_state.s = float(net.headcount)
    else:
        st.session_state.s = float(np.ceil(eq.staffing_requirement(net).sum()))
    st.session_state.ver = st.session_state.get("ver", 0) + 1


def time_series_chart(result: dyn.SimulationResult, values: np.ndarray, names: list[str], y_title: str):
    frame = pd.DataFrame(values, columns=names)
    frame.insert(0, "period", result.times)
    long = frame.melt("period", var_name="department", value_name="value")
    return (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X("period:Q", title="period"),
            y=alt.Y("value:Q", title=y_title),
            color=alt.Color("department:N", sort=names),
            tooltip=["department", alt.Tooltip("period:Q", format=".2f"),
                     alt.Tooltip("value:Q", format=".2f")],
        )
        .properties(height=320)
    )


# --------------------------------------------------------------------------- page
st.set_page_config(page_title="Staffing Equilibrium Optimizer", layout="wide")
st.title("Warehouse Staffing Equilibrium Optimizer")
st.caption(
    "Find the staffing split that keeps every department balanced — and see where a fixed "
    "headcount falls short."
)

with st.sidebar:
    st.header("Scenario")
    files = sorted(EXAMPLES.glob("*.yaml"))
    choice = st.selectbox("Example scenario", [f.name for f in files] or ["(none)"])
    uploaded = st.file_uploader("…or upload a scenario YAML", type=["yaml", "yml"])
    if st.button("Load scenario", width="stretch") or "ver" not in st.session_state:
        if uploaded is not None:
            net0 = io_scenario.loads(uploaded.getvalue().decode("utf-8"))
        else:
            net0 = io_scenario.load_scenario(EXAMPLES / choice)
        load_into_state(net0)

    st.divider()
    t = st.number_input("Time per employee, T", min_value=0.1, value=float(st.session_state.t),
                        step=10.0, help="Productive time one employee supplies per period.")
    s = st.number_input("Headcount, S", min_value=1.0, value=float(st.session_state.s),
                        step=1.0, help="Total closed pool of employees.")

ver = st.session_state.ver
c1, c2 = st.columns(2)
with c1:
    st.subheader("Departments")
    depts = st.data_editor(
        st.session_state.depts, key=f"depts_{ver}", num_rows="dynamic", width="stretch",
        column_config={
            "makespan": st.column_config.NumberColumn("makespan (time/unit)", min_value=0.0, format="%.3f"),
            "demand": st.column_config.NumberColumn("demand (units)", min_value=0.0, format="%.1f"),
            "congestion": st.column_config.NumberColumn("congestion β", min_value=0.0, format="%.3f"),
            "buffer": st.column_config.NumberColumn(
                "buffer (max backlog)", min_value=0.0, format="%.0f",
                help="Max backlog before this department pushes back on its upstream. Blank = unbounded.",
            ),
        },
    )
with c2:
    st.subheader("Routing — fraction of FROM sent to TO")
    routes = st.data_editor(
        st.session_state.routes, key=f"routes_{ver}", num_rows="dynamic", width="stretch",
        column_config={"ratio": st.column_config.NumberColumn("ratio", min_value=0.0, format="%.3f")},
    )

try:
    net = frames_to_net(depts, routes, t, s)
except (ValueError, KeyError) as exc:
    st.error(f"Invalid network: {exc}")
    st.stop()

lam = eq.throughput(net)
required = eq.staffing_requirement(net)
split = eq.staffing_split(net)
feas = gp.feasibility(net, s)
plan_key = "plan_" + "|".join(net.names)

tab_design, tab_eq, tab_dyn, tab_sku = st.tabs(
    ["Design & diagram", "Equilibrium & gaps", "Backlog dynamics", "SKU detail"]
)

# =========================================================== tab 0: design & diagram
with tab_design:
    st.subheader("Design the system in text")
    st.caption(
        "Author departments and flows in the arrow-flow format, see it checked for soundness and "
        "drawn live, then load it into the model. Roots are green; rework loops are dashed red."
    )
    design_text = st.text_area(
        "Design (.flow)", value=dsl.dump_design(net), key=f"design_{ver}", height=300
    )
    result = dsl.parse_design(design_text, name=net.name or "design")

    errors = [d for d in result.diagnostics if d.severity == Severity.ERROR]
    warns = [d for d in result.diagnostics if d.severity == Severity.WARNING]
    infos = [d for d in result.diagnostics if d.severity == Severity.INFO]
    if errors:
        st.error("Not mathematically sound — fix these:\n\n" + "\n".join(f"- {d}" for d in errors))
        if warns:
            st.warning("\n".join(f"- {d}" for d in warns))
    elif warns:
        st.warning("Sound, with warnings:\n\n" + "\n".join(f"- {d}" for d in warns))
    else:
        st.success("Design is mathematically sound.")
    if infos:
        st.caption("  ·  ".join(d.message for d in infos))

    model = (
        dgm.DiagramModel.from_network(result.network)
        if result.network is not None
        else dgm.DiagramModel.from_parse(result)
    )
    st.graphviz_chart(dgm.to_dot(model))

    act_col, dl_col = st.columns([1, 3])
    with act_col:
        if st.button(
            "Load this design",
            disabled=not (result.ok and result.network is not None),
            width="stretch",
        ):
            load_into_state(result.network)
            st.rerun()
    downloads = dl_col.columns(4)
    downloads[0].download_button(".flow", design_text, file_name="design.flow", width="stretch")
    downloads[1].download_button(".dot", dgm.to_dot(model), file_name="design.dot", width="stretch")
    downloads[2].download_button(".mmd", dgm.to_mermaid(model), file_name="design.mmd", width="stretch")
    try:
        import io as _io

        _buf = _io.BytesIO()
        dgm.render_image(model, _buf, fmt="png")
        _buf.seek(0)
        downloads[3].download_button(
            ".png", _buf, file_name="design.png", mime="image/png", width="stretch"
        )
    except RuntimeError:
        downloads[3].caption("PNG: install viz extra")

# =========================================================== tab 1: equilibrium & gaps
with tab_eq:
    st.subheader("System equilibrium")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Required FTE", f"{feas['required_fte']:.1f}")
    m2.metric("Headcount S", f"{s:.0f}")
    m3.metric("Utilization", f"{100 * feas['utilization']:.1f}%")
    m4.metric("Feasible?", "YES" if feas["feasible"] else f"SHORT {feas['shortfall_fte']:.1f} FTE")
    st.caption(
        f"Root departments: {', '.join(net.root_names()) or '(none)'} · "
        f"spectral radius {net.spectral_radius():.3f} · stable: {net.is_stable()}"
    )

    summary = pd.DataFrame(
        {"department": net.names, "throughput": lam, "required FTE": required, "split %": 100 * split}
    )
    left, right = st.columns([1.3, 1])
    with left:
        st.dataframe(
            summary, width="stretch", hide_index=True,
            column_config={
                "throughput": st.column_config.NumberColumn(format="%.1f"),
                "required FTE": st.column_config.NumberColumn(format="%.2f"),
                "split %": st.column_config.NumberColumn(format="%.1f"),
            },
        )
    with right:
        st.bar_chart(summary.set_index("department")["required FTE"], height=260)

    st.subheader("Staffing basis vectors")
    st.caption(
        "Each column is a basis vector: FTE needed across **all** departments per unit of demand "
        "at a root. Any demand plan's staffing is the matching combination of these columns."
    )
    basis = eq.basis_matrix(net)
    roots = net.root_nodes()
    if roots:
        heat = pd.DataFrame(
            [
                {"root": net.names[j], "department": net.names[i], "fte_per_unit": float(basis[i, j])}
                for j in roots
                for i in range(net.n)
            ]
        )
        heat_chart = (
            alt.Chart(heat)
            .mark_rect()
            .encode(
                x=alt.X("root:N", title="unit demand at root", sort=[net.names[j] for j in roots]),
                y=alt.Y("department:N", title=None, sort=net.names),
                color=alt.Color("fte_per_unit:Q", title="FTE / unit", scale=alt.Scale(scheme="blues")),
                tooltip=[
                    alt.Tooltip("root:N"),
                    alt.Tooltip("department:N"),
                    alt.Tooltip("fte_per_unit:Q", title="FTE/unit", format=".4f"),
                ],
            )
            .properties(height=80 + 26 * net.n)
        )
        st.altair_chart(heat_chart, width="stretch")
    else:
        st.info("No root departments detected (every department receives internal rework).")

    st.subheader("Staffing plan & gaps")
    st.caption(
        "Actual staffing is seeded with a suggested allocation of the pool. Edit it to compare "
        "against the requirement: a positive gap means the department is short and will back up."
    )
    plan_default = pd.DataFrame({"department": net.names, "actual FTE": gp.suggested_allocation(net, s)})
    plan = st.data_editor(
        plan_default, key=plan_key, num_rows="fixed", width="stretch",
        column_config={
            "department": st.column_config.TextColumn(disabled=True),
            "actual FTE": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        },
    )
    actual = plan["actual FTE"].astype(float).to_numpy()
    if actual.shape[0] != net.n:
        actual = gp.suggested_allocation(net, s)

    rows = gp.gap_report(net, actual)
    gap_df = pd.DataFrame(
        [
            {"department": r.name, "required": r.required_fte, "actual": r.actual_fte,
             "gap FTE": r.gap_fte, "gap time": r.gap_time, "status": r.status}
            for r in rows
        ]
    )
    gap_chart = (
        alt.Chart(gap_df)
        .mark_bar()
        .encode(
            x=alt.X("department:N", title=None, sort=net.names),
            y=alt.Y("gap FTE:Q", title="gap (FTE):  + short  /  − slack"),
            color=alt.Color(
                "status:N", title="status",
                scale=alt.Scale(domain=["SHORT", "OK", "SLACK"], range=["#d62728", "#9e9e9e", "#2ca02c"]),
            ),
            tooltip=["department", alt.Tooltip("required:Q", format=".2f"),
                     alt.Tooltip("actual:Q", format=".2f"), alt.Tooltip("gap FTE:Q", format="+.2f"), "status"],
        )
    )
    st.altair_chart(gap_chart, width="stretch")
    st.dataframe(
        gap_df, width="stretch", hide_index=True,
        column_config={
            "required": st.column_config.NumberColumn(format="%.2f"),
            "actual": st.column_config.NumberColumn(format="%.2f"),
            "gap FTE": st.column_config.NumberColumn(format="%+.2f"),
            "gap time": st.column_config.NumberColumn("gap (work-time/period)", format="%+.1f"),
        },
    )

# =========================================================== tab 2: backlog dynamics
with tab_dyn:
    st.subheader("Backlog dynamics")
    st.caption(
        "Effective makespan grows as m·exp(β·B), so an under-staffed department's backlog and "
        "makespan run away. With adequate staffing the simulation converges to the equilibrium "
        "throughput λ and backlog stays bounded. β=0 departments never congest."
    )
    bp_on = net.buffer_capacity is not None
    if bp_on:
        capped = [net.names[i] for i in range(net.n) if np.isfinite(net.buffer_capacity[i])]
        st.caption(
            "**Backpressure active** on " + ", ".join(capped) + ": when a department's backlog "
            "fills its buffer it throttles its upstream, so the queue propagates upstream (toward "
            "the root) instead of piling up only at the bottleneck."
        )
    else:
        st.caption(
            "Set a **buffer (max backlog)** on a department (Departments table) to enable "
            "backpressure — a full buffer throttles upstream feeders."
        )
    source = st.radio(
        "Staffing to simulate",
        ["Equilibrium requirement (s*)", "Suggested allocation (S)", "From plan editor"],
        horizontal=True,
    )
    scale = st.slider("Staffing scale factor", 0.50, 1.50, 1.00, 0.05,
                      help="Scale the chosen staffing to induce a shortage (<1) or surplus (>1).")
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    dt = ctrl1.number_input("Δt (periods per step)", 0.005, 1.0, 0.05, step=0.005, format="%.3f")
    horizon = ctrl2.number_input("Horizon (periods)", 1.0, 300.0, 50.0, step=5.0)
    band = ctrl3.slider("Backpressure band", 0.05, 0.5, 0.2, 0.05, disabled=not bp_on,
                        help="Fraction of a buffer's top range over which it throttles upstream.")

    if source.startswith("Equilibrium"):
        base_staffing = required
    elif source.startswith("Suggested"):
        base_staffing = gp.suggested_allocation(net, s)
    else:
        base_staffing = actual  # defined in the equilibrium tab above
    sim_staffing = np.asarray(base_staffing, dtype=float) * scale

    result = dyn.simulate(net, sim_staffing, dt=dt, horizon=horizon, backpressure_band=band)
    diverging = dyn.diverging_departments(result)
    if diverging:
        st.warning("Backlog diverging at: " + ", ".join(net.names[i] for i in diverging))
    else:
        st.success("All departments stable — backlog stays bounded and completions track λ.")

    st.markdown("**Backlog over time** (units waiting)")
    st.altair_chart(time_series_chart(result, result.backlog, net.names, "backlog (units)"), width="stretch")
    st.markdown("**Effective makespan over time** (time per unit)")
    st.altair_chart(
        time_series_chart(result, result.effective_makespan, net.names, "effective makespan"),
        width="stretch",
    )

# =========================================================== tab 3: SKU detail
with tab_sku:
    st.subheader("SKU-level makespan")
    st.caption(
        "Give a makespan per SKU per department and a quantity per SKU (entering at the first "
        "root). The volume-weighted effective makespan feeds the same engine, so basis vectors, "
        "gaps and dynamics all still apply."
    )
    roots = net.root_nodes()
    if not roots:
        st.info("Define a root department (one with no inbound routing) to drive SKU demand.")
    else:
        root0 = roots[0]
        sku_default = pd.DataFrame({"sku": ["A-fast", "B-standard", "C-bulk"],
                                    "quantity": [1500.0, 1800.0, 500.0]})
        for nm in net.names:
            base = float(net.makespan[net.index(nm)])
            sku_default[nm] = [round(base * f, 3) for f in (0.8, 1.0, 1.6)]
        sku_tbl = st.data_editor(sku_default, key=f"sku_{plan_key}", num_rows="dynamic", width="stretch")

        try:
            sku_names = [str(x) for x in sku_tbl["sku"].tolist()]
            quantity = sku_tbl["quantity"].astype(float).fillna(0.0).to_numpy()
            sku_makespan = sku_tbl[list(net.names)].astype(float).to_numpy()
            sku_demand = np.zeros((len(sku_names), net.n))
            sku_demand[:, root0] = quantity
            workload = sku.sku_workload(net, sku_makespan, sku_demand, skus=sku_names)
            agg = sku.aggregate_network(net, sku_makespan, sku_demand)
        except (ValueError, KeyError) as exc:
            st.error(f"Could not resolve SKU workload: {exc}")
            st.stop()

        sku_feas = gp.feasibility(agg, s)
        d1, d2 = st.columns(2)
        d1.metric("SKU-resolved required FTE", f"{workload.required_fte.sum():.1f}",
                  delta=f"{workload.required_fte.sum() - required.sum():+.1f} vs base")
        d2.metric("Utilization", f"{100 * sku_feas['utilization']:.1f}%")

        out = pd.DataFrame(
            {
                "department": net.names,
                "throughput": workload.total_units,
                "effective makespan": workload.effective_makespan,
                "required FTE": workload.required_fte,
                "split %": 100 * eq.staffing_split(agg),
            }
        )
        st.dataframe(
            out, width="stretch", hide_index=True,
            column_config={
                "throughput": st.column_config.NumberColumn(format="%.1f"),
                "effective makespan": st.column_config.NumberColumn(format="%.3f"),
                "required FTE": st.column_config.NumberColumn(format="%.2f"),
                "split %": st.column_config.NumberColumn(format="%.1f"),
            },
        )
