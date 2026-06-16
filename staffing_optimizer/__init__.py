"""Warehouse staffing equilibrium optimizer.

Model a network of departments that send work to each other in fixed ratios, then deliver:

- **basis vectors** mapping demand to a system-wide staffing requirement (``basis_matrix``),
- the **staffing split** that keeps every department balanced (``staffing_split``), and
- **makespan gaps / staffing shorts** against a closed headcount (``gap_report``).

Quick start::

    import staffing_optimizer as so

    net = so.load_scenario("examples/warehouse_5dept.yaml")
    so.staffing_split(net)                        # balanced staffing fractions
    print(so.format_report(net, headcount=50))    # full text report

CLIs: ``python solve.py <scenario.yaml>`` (headless report) and
``python design.py <design.flow>`` (validate + draw a design). Interactive app:
``streamlit run app/dashboard.py``. Each module has a ``Usage`` block showing its own API.
"""
from staffing_optimizer.diagnostics import Diagnostic, Severity, diagnose
from staffing_optimizer.diagram import DiagramModel, render_image, to_dot, to_mermaid
from staffing_optimizer.dsl import DesignParseResult, dump_design, parse_design
from staffing_optimizer.dynamics import (
    SimulationResult,
    backlog_slope,
    diverging_departments,
    simulate,
)
from staffing_optimizer.equilibrium import (
    allocate_headcount,
    basis_matrix,
    leontief_inverse,
    staffing_requirement,
    staffing_split,
    throughput,
)
from staffing_optimizer.gaps import (
    GapRow,
    feasibility,
    gap_report,
    staffing_gaps,
    suggested_allocation,
)
from staffing_optimizer.io_scenario import (
    load_scenario,
    load_scenario_csv,
    loads,
    save_scenario,
)
from staffing_optimizer.network import DepartmentNetwork
from staffing_optimizer.report import format_report
from staffing_optimizer.skus import SkuWorkload, aggregate_network, sku_workload

__version__ = "0.1.0"

__all__ = [
    "DepartmentNetwork",
    "throughput",
    "leontief_inverse",
    "basis_matrix",
    "staffing_requirement",
    "staffing_split",
    "allocate_headcount",
    "staffing_gaps",
    "feasibility",
    "gap_report",
    "suggested_allocation",
    "GapRow",
    "load_scenario",
    "load_scenario_csv",
    "loads",
    "save_scenario",
    "format_report",
    "simulate",
    "SimulationResult",
    "backlog_slope",
    "diverging_departments",
    "sku_workload",
    "aggregate_network",
    "SkuWorkload",
    "parse_design",
    "dump_design",
    "DesignParseResult",
    "diagnose",
    "Diagnostic",
    "Severity",
    "DiagramModel",
    "to_dot",
    "to_mermaid",
    "render_image",
]
