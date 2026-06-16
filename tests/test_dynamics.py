import numpy as np
import pytest

from staffing_optimizer import dynamics as dyn
from staffing_optimizer import equilibrium as eq
from staffing_optimizer.network import DepartmentNetwork


def chain_net(congestion=(0.0, 0.05, 0.0)) -> DepartmentNetwork:
    # A -> B -> C; lambda = [100, 100, 100]; requirement s* = [200, 100, 50] (T = 1).
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0
    routing[2, 1] = 1.0
    return DepartmentNetwork(
        ["A", "B", "C"],
        routing,
        demand=[100, 0, 0],
        makespan=[2.0, 1.0, 0.5],
        time_per_employee=1.0,
        congestion=list(congestion),
    )


def test_stable_dynamics_converges_to_equilibrium():
    net = chain_net()
    staffing = 2.0 * eq.staffing_requirement(net)  # ample
    result = dyn.simulate(net, staffing, dt=0.05, horizon=30.0)
    assert result.final_completions == pytest.approx(eq.throughput(net), rel=1e-3)
    assert result.final_backlog == pytest.approx([0, 0, 0], abs=1e-6)
    assert dyn.diverging_departments(result) == []


def test_understaffed_department_diverges_and_makespan_blows_up():
    net = chain_net()
    staffing = eq.staffing_requirement(net).copy()
    staffing[1] = 30.0  # B needs 100; starve it
    result = dyn.simulate(net, staffing, dt=0.05, horizon=30.0)
    assert dyn.diverging_departments(result) == [1]
    assert result.final_backlog[1] > 100.0
    # effective makespan at the congested department grows far beyond its base value
    assert result.effective_makespan[-1, 1] > 10.0 * net.makespan[1]
    # the unaffected root never backs up
    assert result.final_backlog[0] == pytest.approx(0.0, abs=1e-6)


def test_zero_congestion_keeps_makespan_constant():
    net = chain_net(congestion=(0.0, 0.0, 0.0))
    staffing = eq.staffing_requirement(net).copy()
    staffing[1] = 30.0  # still starved, so backlog grows...
    result = dyn.simulate(net, staffing, dt=0.05, horizon=20.0)
    assert 1 in dyn.diverging_departments(result)
    # ...but with beta = 0 the effective makespan never changes.
    assert np.allclose(result.effective_makespan[:, 1], net.makespan[1])


def _bare_chain(buffer_capacity=None):
    routing = np.zeros((3, 3))
    routing[1, 0] = 1.0  # A -> B
    routing[2, 1] = 1.0  # B -> C
    return DepartmentNetwork(
        ["A", "B", "C"], routing, demand=[100, 0, 0], makespan=[1.0, 1.0, 1.0],
        time_per_employee=1.0, buffer_capacity=buffer_capacity,
    )


def test_backpressure_propagates_backlog_upstream():
    staffing = [100, 100, 40]  # C is the downstream bottleneck
    open_run = dyn.simulate(_bare_chain(), staffing, dt=0.05, horizon=60.0)
    bp_run = dyn.simulate(_bare_chain([np.inf, 50, 50]), staffing, dt=0.05, horizon=60.0)

    # Without backpressure only the bottleneck C backs up; the root A stays clear.
    assert open_run.final_backlog[0] < 1.0
    assert dyn.diverging_departments(open_run) == [2]

    # With backpressure the queue propagates to the root; C stays bounded near its buffer.
    assert bp_run.final_backlog[0] > 100.0
    assert bp_run.final_backlog[2] < open_run.final_backlog[2]
    assert 0 in dyn.diverging_departments(bp_run)


def test_backpressure_preserves_equilibrium_with_adequate_staffing():
    net = _bare_chain([np.inf, 50, 50])
    result = dyn.simulate(net, 2.0 * eq.staffing_requirement(net), dt=0.05, horizon=30.0)
    assert result.final_completions == pytest.approx(eq.throughput(net), rel=1e-3)
    assert dyn.diverging_departments(result) == []


def test_invalid_backpressure_band_raises():
    with pytest.raises(ValueError):
        dyn.simulate(_bare_chain(), [100, 100, 100], backpressure_band=0.0)
