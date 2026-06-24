# Warehouse Staffing Equilibrium Optimizer

Model a warehouse as a network of departments that hand work to each other in fixed ratios,
then answer: **with a fixed pool of employees, what staffing split keeps every department's
throughput matched to its inflow so nothing backs up — and where the pool is too small, which
departments are short, and by how much?**

## The model

Let there be `n` departments.

| symbol | meaning |
| --- | --- |
| `P` (n×n) | routing matrix; `P[i, j]` = fraction of dept *j*'s output that becomes dept *i*'s work |
| `d` (n,) | exogenous demand per period (inbound work). **Root** depts have an all-zero `P` row and receive only `d` |
| `m` (n,) | makespan: processing time per unit, per employee |
| `T` | productive time one employee supplies per period (e.g. 480 min/shift) |
| `S` | closed headcount (total employees) |

**Equilibrium throughput** (flow balance / Leontief):

```
lambda = d + P @ lambda      =>      lambda = (I - P)^-1 @ d
```

**Basis vectors.** The staffing basis matrix `M = (1/T) · diag(m) · (I - P)^-1` maps demand to
required full-time-equivalents: `s* = M @ d`. Each **column `M[:, j]` is a basis vector** — the
staffing footprint across *all* departments caused by one unit of demand at root node *j*.

**Staffing split** `s* / Σs*` (fractions summing to 1) is the balanced allocation; against any
actual staffing `s`, the **gap** `s*_i - s_i` is positive when a department is short (it will back
up) and negative when it has slack. Multiplying by `T` expresses the gap as work-time/period.

A network is rejected when the routing spectral radius reaches 1 (rework never drains).

**Dynamic congestion** (`dynamics.py`): a time-stepped simulation where backlog `B_i` drives an
exponentially growing effective makespan `m_eff = m · exp(β·B)` — the "backed-up" slowdown — with
`β = 0` marking departments that don't congest. Each step routes the previous step's completions
downstream (Jacobi iteration for `λ`), so with adequate staffing it converges to the equilibrium
above and backlog stays bounded; under-staff a department and its backlog and makespan run away.

**Backpressure**: give a department a `buffer` (max backlog) and, as its backlog fills that buffer,
it throttles its upstream feeders — so under overload the queue **propagates upstream** toward the
root (whose external demand can't be throttled) instead of piling up only at the bottleneck. The
throttle only engages near-full, so adequate staffing still converges to `λ`. No `buffer` set =
unbounded (no backpressure).

**SKU-level makespan** (`skus.py`): supply a makespan per SKU per department and SKU demand; each
SKU's throughput is `(I − P)⁻¹ d_k`, and the volume-weighted effective makespan collapses back to
a single-makespan network that feeds the same engine unchanged.

## Install

```bash
pip install -e .            # core (numpy, pyyaml)
pip install -e ".[web]"     # + the web app (fastapi, uvicorn, jinja2)
pip install -e ".[viz]"     # + PNG diagram export (matplotlib, networkx)
pip install -e ".[dev]"     # + pytest, ruff, httpx
```

## Run the app (primary)

A local web app: visually build a system, validate it, save/transfer it, then run interactive
time-step simulations and see the staffing analysis.

```bash
python -m webapp            # http://localhost:8000
```

- **Builder** (`/builder`) — drag department nodes onto a canvas, draw flow edges, edit
  makespan/demand/congestion/buffer, **Validate** (roots highlighted, rework dashed/red, diagnostics),
  and **Save** (timestamped).
- **Saved designs** (`/designs`) — library with valid/invalid badges; **Export**/**Import** a system
  as `.json`/`.flow`/`.yaml` for easy transfer; Open / Simulate / Analyze.
- **Simulate** (`/simulate/{id}`) — Play / Pause / Step / scrub a time cursor; backlog & effective-
  makespan charts grow per step and diagram nodes shade by backlog. A design must validate to run.
- **Analyze** (`/analyze/{id}`) — staffing split, feasibility, SHORT/OK/SLACK gaps, basis vectors.

## CLI / library

Headless report:

```bash
python solve.py examples/warehouse_5dept.yaml
python solve.py examples/warehouse_5dept.yaml --actual 15,11,10,7,4
```

> The earlier **Streamlit dashboard** (`streamlit run app/dashboard.py`, needs `.[app]`) is
> **deprecated** — superseded by the web app above. It still works but is no longer maintained as
> the primary UI.

## Design interface (author → validate → diagram)

For stakeholders to "draw in" a system as plain text, validate its math soundness, and see it
drawn before simulating. Author an arrow-flow `.flow` file (department blocks + `A -> B : ratio`
lines — see [examples/warehouse_5dept.flow](examples/warehouse_5dept.flow)), then:

```bash
python design.py examples/warehouse_5dept.flow            # report soundness, write .dot + .mmd
python design.py examples/warehouse_5dept.flow --image    # also render a PNG (needs the viz extra)
python design.py examples/warehouse_5dept.flow --to-yaml scenario.yaml   # convert to engine YAML
```

The report lists line-referenced **errors** (missing makespan, undefined department, unstable
rework loop), **warnings** (no root, unreachable department, demand on a non-root) and an **info**
feasibility summary; exit code is 1 if anything is unsound. The diagram is a left-to-right
block-and-arrow graph — roots highlighted, rework loops dashed/red, nodes labeled with
makespan/demand/throughput. The dashboard's **Design & diagram** tab does the same live (Graphviz,
no install) and loads a sound design into the other tabs.

As a library:

```python
from staffing_optimizer import load_scenario, basis_matrix, staffing_split, gap_report

net = load_scenario("examples/warehouse_5dept.yaml")
M = basis_matrix(net)                 # columns = per-root basis vectors
split = staffing_split(net)           # balanced staffing fractions
rows = gap_report(net, actual=[15, 11, 10, 7, 4])  # per-dept SHORT / OK / SLACK
```

## Layout

```
staffing_optimizer/   network · equilibrium · gaps · report · io_scenario   (core, numpy only)
                      dynamics (backlog simulation) · skus (SKU makespan lookup)
                      dsl (arrow-flow format) · diagnostics (soundness) · diagram (DOT/Mermaid/PNG)
webapp/               FastAPI site: app · api · store (timestamped designs) · adapters (engine bridge)
                      templates/ + static/ (Cytoscape builder, Chart.js playback)   <- primary UI
app/dashboard.py      Streamlit dashboard (deprecated; superseded by webapp/)
examples/             sample scenarios (.yaml node/edge tables; .flow arrow-flow design)
solve.py              headless equilibrium report   ·   design.py  validate + diagram a design
tests/                math checks (chain, analytic inverse, basis linearity, rework series,
                      dynamics convergence/divergence, SKU makespan, DSL/diagnostics/diagram)
```

The `viz` extra (`pip install -e ".[viz]"`, matplotlib + networkx) is only needed for PNG export;
the in-app diagram and the DOT/Mermaid text exports need nothing beyond the core.
