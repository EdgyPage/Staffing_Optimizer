"""Streamlit dashboard for the warehouse staffing equilibrium optimizer.

Edit departments, routing ratios, demand and headcount, and watch the equilibrium staffing
split, the basis vectors and the per-department makespan gaps update live.

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

from staffing_optimizer import equilibrium as eq  # noqa: E402
from staffing_optimizer import gaps as gp  # noqa: E402
from staffing_optimizer import io_scenario  # noqa: E402
from staffing_optimizer.network import DepartmentNetwork  # noqa: E402

EXAMPLES = ROOT / "examples"


# --------------------------------------------------------------------------- helpers
def net_to_frames(net: DepartmentNetwork) -> tuple[pd.DataFrame, pd.DataFrame]:
    depts = pd.DataFrame(
        {
            "department": net.names,
            "makespan": net.makespan,
            "demand": net.demand,
            "congestion": net.congestion if net.congestion is not None else np.zeros(net.n),
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
    names, makespan, demand, congestion = [], [], [], []
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

    idx = {nm: i for i, nm in enumerate(names)}
    routing = np.zeros((len(names), len(names)))
    for _, r in routes.iterrows():
        frm = str(r.get("from", "") or "").strip()
        to = str(r.get("to", "") or "").strip()
        ratio = r.get("ratio")
        if frm in idx and to in idx and pd.notna(ratio):
            routing[idx[to], idx[frm]] = float(ratio)

    return DepartmentNetwork(
        names=names,
        routing=routing,
        demand=np.array(demand),
        makespan=np.array(makespan),
        time_per_employee=t,
        headcount=s,
        congestion=np.array(congestion),
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
    {
        "department": net.names,
        "throughput": lam,
        "required FTE": required,
        "split %": 100 * split,
    }
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
    "Each column is a basis vector: FTE needed across **all** departments per unit of demand at "
    "a root. Any demand plan's staffing is the matching combination of these columns."
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
    "Actual staffing is seeded with a suggested allocation of the pool. Edit it to compare against "
    "the requirement: a positive gap means the department is short and will back up."
)
plan_key = "plan_" + "|".join(net.names)
plan_default = pd.DataFrame(
    {"department": net.names, "actual FTE": gp.suggested_allocation(net, s)}
)
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
        {
            "department": r.name,
            "required": r.required_fte,
            "actual": r.actual_fte,
            "gap FTE": r.gap_fte,
            "gap time": r.gap_time,
            "status": r.status,
        }
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
            "status:N",
            title="status",
            scale=alt.Scale(domain=["SHORT", "OK", "SLACK"], range=["#d62728", "#9e9e9e", "#2ca02c"]),
        ),
        tooltip=[
            "department",
            alt.Tooltip("required:Q", format=".2f"),
            alt.Tooltip("actual:Q", format=".2f"),
            alt.Tooltip("gap FTE:Q", format="+.2f"),
            "status",
        ],
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

st.caption(
    "Phase 2 (planned): a Dynamics tab with the time-stepped exponential-backlog simulation, and "
    "a SKU tab for per-SKU makespan lookup."
)
