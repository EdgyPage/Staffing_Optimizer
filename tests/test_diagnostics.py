import numpy as np

from staffing_optimizer import diagnostics as dg
from staffing_optimizer.diagnostics import Severity
from staffing_optimizer.dsl import parse_design
from staffing_optimizer.network import DepartmentNetwork


def test_sound_design_has_no_errors():
    result = parse_design(
        "Root [makespan=1, demand=10]\nRoot -> Mid : 1.0\nMid [makespan=1]\n"
    )
    assert result.ok
    assert not any(d.severity == Severity.ERROR for d in result.diagnostics)


def test_no_root_warns():
    net = DepartmentNetwork(["A", "B"], [[0, 0.5], [0.5, 0]], demand=[0, 0], makespan=[1, 1])
    diags = dg.diagnose(net)
    assert any(d.severity == Severity.WARNING and "root" in d.message.lower() for d in diags)


def test_unreachable_department_warns():
    routing = np.zeros((4, 4))
    routing[1, 0] = 1.0   # A -> B
    routing[3, 2] = 0.5   # C -> D
    routing[2, 3] = 0.5   # D -> C  (closed pair, disconnected from the root A)
    net = DepartmentNetwork(["A", "B", "C", "D"], routing, demand=[10, 0, 0, 0], makespan=[1, 1, 1, 1])
    assert {net.names[i] for i in dg.unreachable_departments(net)} == {"C", "D"}
    assert any("unreachable" in d.message for d in dg.diagnose(net))


def test_demand_on_non_root_warns():
    routing = np.zeros((2, 2))
    routing[1, 0] = 1.0  # A -> B
    net = DepartmentNetwork(["A", "B"], routing, demand=[10, 5], makespan=[1, 1])
    diags = dg.diagnose(net)
    assert any(d.severity == Severity.WARNING and "demand" in d.message.lower() for d in diags)


def test_fan_out_is_info():
    routing = np.zeros((3, 3))
    routing[1, 0] = 0.8
    routing[2, 0] = 0.8  # A sends out 1.6x its work
    net = DepartmentNetwork(["A", "B", "C"], routing, demand=[10, 0, 0], makespan=[1, 1, 1])
    assert any(d.severity == Severity.INFO and "fan-out" in d.message for d in dg.diagnose(net))


def test_unstable_rework_is_error_naming_the_loop():
    result = parse_design(
        "A [makespan=1, demand=10]\nA -> B : 1.0\nB [makespan=1]\nB -> A : 1.0\n"
    )
    assert not result.ok
    assert result.network is None
    assert any(
        d.severity == Severity.ERROR and "spectral radius" in d.message and "loop" in d.message.lower()
        for d in result.diagnostics
    )


def test_back_edges_picks_one_side_of_a_two_cycle():
    # A -> B and B -> A; starting from A, only B -> A is a back edge.
    assert dg.back_edges(2, [(0, 1), (1, 0)], order=[0, 1]) == {(1, 0)}
