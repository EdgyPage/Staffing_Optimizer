import numpy as np

from staffing_optimizer.diagnostics import Severity
from staffing_optimizer.dsl import dump_design, parse_design

EXAMPLE = """
period_time = 480
headcount = 50

Receiving [makespan=2.0, demand=3800]
Putaway   [makespan=1.5, congestion=0.02]
Picking   [makespan=1.0, congestion=0.03]
Packing   [makespan=0.8, congestion=0.02]
Shipping  [makespan=0.5]

Receiving -> Putaway  : 1.0
Putaway   -> Picking  : 1.0
Picking   -> Packing  : 1.0
Packing   -> Shipping : 1.0
Packing   -> Picking  : 0.10   # rework
Shipping  -> Packing  : 0.05   # rework
"""


def test_parse_example_builds_network():
    result = parse_design(EXAMPLE)
    assert result.ok
    net = result.network
    assert net is not None
    assert net.names == ["Receiving", "Putaway", "Picking", "Packing", "Shipping"]
    assert net.time_per_employee == 480
    assert net.headcount == 50
    assert net.routing[net.index("Putaway"), net.index("Receiving")] == 1.0
    assert net.routing[net.index("Picking"), net.index("Packing")] == 0.10
    assert net.congestion[net.index("Picking")] == 0.03
    assert net.demand[net.index("Receiving")] == 3800


def test_round_trip_through_dump():
    net = parse_design(EXAMPLE).network
    net2 = parse_design(dump_design(net)).network
    assert net2.names == net.names
    assert np.allclose(net2.routing, net.routing)
    assert np.allclose(net2.makespan, net.makespan)
    assert np.allclose(net2.demand, net.demand)
    assert np.allclose(net2.congestion, net.congestion)
    assert net2.time_per_employee == net.time_per_employee
    assert net2.headcount == net.headcount


def test_undefined_reference_is_a_line_referenced_error():
    result = parse_design("A [makespan=1]\nA -> B : 1.0\n")
    assert not result.ok
    assert result.network is None
    assert any(
        d.severity == Severity.ERROR and "undefined" in d.message and d.line == 2
        for d in result.diagnostics
    )


def test_missing_makespan_is_error():
    result = parse_design("A [demand=5]\n")
    assert not result.ok
    assert any(d.severity == Severity.ERROR and "makespan" in d.message for d in result.diagnostics)


def test_non_numeric_value_is_error():
    result = parse_design("A [makespan=foo]\n")
    assert not result.ok
    assert any(d.severity == Severity.ERROR for d in result.diagnostics)


def test_duplicate_department_is_error():
    result = parse_design("A [makespan=1]\nA [makespan=2]\n")
    assert any(
        d.severity == Severity.ERROR and "more than once" in d.message for d in result.diagnostics
    )


def test_department_order_does_not_matter():
    # Mid is referenced before it is defined; still fine.
    result = parse_design("Root [makespan=1, demand=10]\nRoot -> Mid : 1.0\nMid [makespan=1]\n")
    assert result.ok
    assert result.network.names == ["Root", "Mid"]
