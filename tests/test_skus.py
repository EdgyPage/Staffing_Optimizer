import numpy as np
import pytest

from staffing_optimizer import equilibrium as eq
from staffing_optimizer import skus
from staffing_optimizer.network import DepartmentNetwork


def chain_net() -> DepartmentNetwork:
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0
    routing[2, 1] = 1.0
    return DepartmentNetwork(
        ["A", "B", "C"], routing, demand=[120, 0, 0], makespan=[2.0, 1.0, 0.5], time_per_employee=8.0
    )


def test_single_sku_matches_base_network():
    net = chain_net()
    sku_makespan = [[2.0, 1.0, 0.5]]      # one SKU, same makespan as the base
    sku_demand = [[120.0, 0.0, 0.0]]      # entering at the root
    agg = skus.aggregate_network(net, sku_makespan, sku_demand)
    assert agg.makespan == pytest.approx(net.makespan)
    assert eq.staffing_requirement(agg) == pytest.approx(eq.staffing_requirement(net))


def test_effective_makespan_reproduces_sku_workload():
    net = chain_net()
    sku_makespan = np.array([[2.0, 1.0, 0.5], [3.0, 0.5, 1.0]])
    sku_demand = np.array([[80.0, 0.0, 0.0], [40.0, 0.0, 0.0]])

    workload = skus.sku_workload(net, sku_makespan, sku_demand)
    leontief = eq.leontief_inverse(net)
    expected_work_time = sum(
        (leontief @ sku_demand[k]) * sku_makespan[k] for k in range(2)
    )
    assert workload.work_time == pytest.approx(expected_work_time)
    assert workload.required_fte == pytest.approx(expected_work_time / net.time_per_employee)

    agg = skus.aggregate_network(net, sku_makespan, sku_demand)
    assert eq.staffing_requirement(agg) == pytest.approx(workload.required_fte)


def test_aggregate_network_supports_split():
    net = chain_net()
    sku_makespan = np.array([[2.0, 1.0, 0.5], [3.0, 0.5, 1.0]])
    sku_demand = np.array([[80.0, 0.0, 0.0], [40.0, 0.0, 0.0]])
    agg = skus.aggregate_network(net, sku_makespan, sku_demand)
    assert eq.staffing_split(agg).sum() == pytest.approx(1.0)


def test_positive_makespan_enforced():
    net = chain_net()
    with pytest.raises(ValueError):
        skus.sku_workload(net, [[2.0, 0.0, 0.5]], [[120.0, 0.0, 0.0]])
