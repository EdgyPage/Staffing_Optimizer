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

**SKU-level makespan** (`skus.py`): supply a makespan per SKU per department and SKU demand; each
SKU's throughput is `(I − P)⁻¹ d_k`, and the volume-weighted effective makespan collapses back to
a single-makespan network that feeds the same engine unchanged.

## Install

```bash
pip install -e .            # core (numpy, pyyaml)
pip install -e ".[app]"     # + Streamlit dashboard (streamlit, altair, pandas)
pip install -e ".[dev]"     # + pytest, ruff
```

## Use

Headless report:

```bash
python solve.py examples/warehouse_5dept.yaml
python solve.py examples/warehouse_5dept.yaml --actual 15,11,10,7,4
```

Interactive dashboard (edit ratios/demand/headcount and watch the split and gaps update live):

```bash
streamlit run app/dashboard.py
```

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
app/dashboard.py      Streamlit dashboard: Equilibrium & gaps / Backlog dynamics / SKU detail tabs
examples/             sample scenarios (YAML: node table + routing edge list)
solve.py              headless report entry point
tests/                math checks (chain, analytic inverse, basis linearity, rework series,
                      dynamics convergence/divergence, SKU effective makespan)
```
