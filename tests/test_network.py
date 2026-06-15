import numpy as np
import pytest

from staffing_optimizer.network import DepartmentNetwork


def chain(ratio: float = 1.0) -> DepartmentNetwork:
    """A -> B -> C linear chain with demand entering at A."""
    routing = np.zeros((3, 3))
    routing[1, 0] = ratio  # A -> B
    routing[2, 1] = ratio  # B -> C
    return DepartmentNetwork(["A", "B", "C"], routing, demand=[100, 0, 0], makespan=[1, 1, 1])


def test_root_detection():
    assert chain().root_names() == ["A"]


def test_edge_list_builds_expected_matrix():
    net = chain()
    assert net.routing.shape == (3, 3)
    assert net.routing[1, 0] == 1.0  # A -> B
    assert net.routing[2, 1] == 1.0  # B -> C
    assert net.routing[0, 0] == 0.0


def test_makespan_must_be_positive():
    with pytest.raises(ValueError):
        DepartmentNetwork(["A"], np.zeros((1, 1)), demand=[1.0], makespan=[0.0])


def test_negative_routing_rejected():
    with pytest.raises(ValueError):
        DepartmentNetwork(["A", "B"], [[0, -0.1], [0, 0]], demand=[1, 1], makespan=[1, 1])


def test_shape_mismatch_rejected():
    with pytest.raises(ValueError):
        DepartmentNetwork(["A", "B"], np.zeros((2, 2)), demand=[1, 2, 3], makespan=[1, 1])


def test_spectral_radius_gate_rejects_undraining_loop():
    # A self-loop with ratio 1 never drains -> spectral radius 1 -> rejected.
    with pytest.raises(ValueError):
        DepartmentNetwork(["A"], [[1.0]], demand=[1.0], makespan=[1.0])


def test_rework_loop_below_one_is_stable():
    net = DepartmentNetwork(["A"], [[0.5]], demand=[1.0], makespan=[1.0])
    assert net.is_stable()
    assert net.spectral_radius() == pytest.approx(0.5)
