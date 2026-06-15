import numpy as np
import pytest

from staffing_optimizer import equilibrium as eq
from staffing_optimizer import gaps
from staffing_optimizer.network import DepartmentNetwork


def make_net(headcount: float = 300.0) -> DepartmentNetwork:
    # A -> B -> C chain; requirement s* = [200, 100, 50] (m=[2,1,0.5], lambda=[100,100,100], T=1).
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0
    routing[2, 1] = 1.0
    return DepartmentNetwork(
        ["A", "B", "C"],
        routing,
        demand=[100, 0, 0],
        makespan=[2.0, 1.0, 0.5],
        headcount=headcount,
        congestion=[0.0, 0.1, 0.0],
    )


def test_feasible_when_pool_covers_requirement():
    feas = gaps.feasibility(make_net(headcount=400))
    assert feas["required_fte"] == pytest.approx(350.0)
    assert feas["feasible"] is True
    assert feas["utilization"] == pytest.approx(350 / 400)
    assert feas["shortfall_fte"] == 0.0


def test_infeasible_reports_shortfall():
    feas = gaps.feasibility(make_net(headcount=300))
    assert feas["feasible"] is False
    assert feas["shortfall_fte"] == pytest.approx(50.0)


def test_gap_signs_and_status():
    net = make_net()
    rows = {r.name: r for r in gaps.gap_report(net, actual=[200, 80, 60])}
    assert rows["A"].status == "OK"
    assert rows["B"].status == "SHORT"
    assert rows["B"].gap_fte == pytest.approx(20.0)
    assert rows["B"].gap_time == pytest.approx(20.0 * net.time_per_employee)
    assert rows["C"].status == "SLACK"
    assert rows["C"].gap_fte == pytest.approx(-10.0)


def test_suggested_allocation_conserves_headcount_and_buffers_congested_dept():
    net = make_net(headcount=400)
    alloc = gaps.suggested_allocation(net)
    assert alloc.sum() == pytest.approx(400.0)
    # 50 FTE of slack should buffer the only congestion-prone department (B).
    required = eq.staffing_requirement(net)
    assert alloc[1] - required[1] == pytest.approx(50.0)
    assert alloc[0] == pytest.approx(required[0])
    assert alloc[2] == pytest.approx(required[2])


def test_suggested_allocation_proportional_when_infeasible():
    net = make_net(headcount=175)  # half of the 350 requirement
    alloc = gaps.suggested_allocation(net)
    assert alloc.sum() == pytest.approx(175.0)
    assert alloc == pytest.approx(eq.staffing_requirement(net) * 0.5)
