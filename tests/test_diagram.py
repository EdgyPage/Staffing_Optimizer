import pytest

from staffing_optimizer.diagram import DiagramModel, to_dot, to_mermaid, render_image
from staffing_optimizer.dsl import parse_design

ROOTED = (
    "Root [makespan=2, demand=100]\n"
    "A [makespan=1]\n"
    "B [makespan=1]\n"
    "Root -> A : 1.0\n"
    "A -> B : 1.0\n"
    "B -> A : 0.2\n"   # rework
)

UNSTABLE = "A [makespan=1, demand=10]\nA -> B : 1.0\nB [makespan=1]\nB -> A : 1.0\n"


def test_to_dot_has_nodes_rework_and_root_styling():
    model = DiagramModel.from_network(parse_design(ROOTED).network)
    dot = to_dot(model)
    assert "digraph" in dot
    for name in ("Root", "A", "B"):
        assert f'"{name}"' in dot
    assert "dashed" in dot          # B -> A rework edge
    assert "#d9f0d9" in dot         # Root highlighted


def test_to_mermaid_is_a_flowchart():
    model = DiagramModel.from_network(parse_design(ROOTED).network)
    mermaid = to_mermaid(model)
    assert mermaid.startswith("flowchart")
    assert "Root" in mermaid and ".->" in mermaid  # dotted rework edge: `-. "0.2" .->`


def test_from_parse_renders_even_when_invalid():
    result = parse_design(UNSTABLE)
    assert result.network is None
    dot = to_dot(DiagramModel.from_parse(result))
    assert '"A"' in dot and '"B"' in dot


def test_render_image_writes_a_png(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("networkx")
    model = DiagramModel.from_network(parse_design(ROOTED).network)
    out = tmp_path / "diagram.png"
    render_image(model, str(out))
    assert out.exists() and out.stat().st_size > 0
