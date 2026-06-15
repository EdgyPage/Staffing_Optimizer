import numpy as np
import pytest

from staffing_optimizer import equilibrium as eq
from staffing_optimizer.network import DepartmentNetwork


def test_chain_throughput_and_requirement():
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0  # A -> B
    routing[2, 1] = 1.0  # B -> C
    net = DepartmentNetwork(
        ["A", "B", "C"], routing, demand=[100, 0, 0], makespan=[2.0, 1.5, 0.5]
    )
    assert eq.throughput(net) == pytest.approx([100, 100, 100])
    # s* = m * lambda / T, with T = 1
    assert eq.staffing_requirement(net) == pytest.approx([200, 150, 50])


def test_2x2_matches_analytic_leontief_inverse():
    # node 0 receives half of node 1's output; node 1 is the root.
    routing = np.array([[0.0, 0.5], [0.0, 0.0]])
    net = DepartmentNetwork(["mix", "root"], routing, demand=[0.0, 10.0], makespan=[1.0, 1.0])
    np.testing.assert_allclose(eq.leontief_inverse(net), [[1.0, 0.5], [0.0, 1.0]])
    assert eq.throughput(net) == pytest.approx([5.0, 10.0])


def test_rework_loop_gives_geometric_series_throughput():
    r = 0.5
    net = DepartmentNetwork(["A"], [[r]], demand=[1.0], makespan=[1.0])
    assert eq.throughput(net)[0] == pytest.approx(1.0 / (1.0 - r))


def test_basis_matrix_reproduces_requirement_and_is_linear():
    routing = np.array(
        [
            [0.0, 0.0, 0.0],  # R is a root
            [0.6, 0.0, 0.2],  # B receives 0.6 of R and 0.2 of C
            [0.4, 0.0, 0.0],  # C receives 0.4 of R
        ]
    )
    net = DepartmentNetwork(
        ["R", "B", "C"], routing, demand=[50, 0, 0], makespan=[2.0, 1.0, 1.5], time_per_employee=8.0
    )
    basis = eq.basis_matrix(net)
    # s* == M @ d
    assert basis @ net.demand == pytest.approx(eq.staffing_requirement(net))
    # columns act as basis vectors: linearity over demand
    d1 = np.array([10.0, 0.0, 0.0])
    d2 = np.array([0.0, 0.0, 5.0])
    assert basis @ (d1 + d2) == pytest.approx(basis @ d1 + basis @ d2)


def test_split_sums_to_one_and_allocation_scales():
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0
    routing[2, 1] = 1.0
    net = DepartmentNetwork(["A", "B", "C"], routing, demand=[100, 0, 0], makespan=[2, 1, 1])
    assert eq.staffing_split(net).sum() == pytest.approx(1.0)
    assert eq.allocate_headcount(net, 90).sum() == pytest.approx(90.0)
