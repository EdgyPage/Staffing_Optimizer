import pytest
from fastapi.testclient import TestClient

from webapp import store
from webapp.app import app

SOUND = {
    "name": "chain",
    "settings": {"time_per_employee": 1, "headcount": 300},
    "departments": [
        {"name": "A", "makespan": 2, "demand": 100},
        {"name": "B", "makespan": 1},
        {"name": "C", "makespan": 0.5},
    ],
    "flows": [{"from": "A", "to": "B", "ratio": 1.0}, {"from": "B", "to": "C", "ratio": 1.0}],
}

FAULTY = {  # A <-> B with ratio 1 each way: spectral radius 1, never drains
    "name": "loop",
    "settings": {"time_per_employee": 1},
    "departments": [{"name": "A", "makespan": 1, "demand": 10}, {"name": "B", "makespan": 1}],
    "flows": [{"from": "A", "to": "B", "ratio": 1.0}, {"from": "B", "to": "A", "ratio": 1.0}],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DESIGNS_DIR", tmp_path)  # isolate persistence
    with TestClient(app) as c:
        yield c


def _new(client, doc):
    return client.post("/api/designs", json=doc).json()["id"]


def test_validate_sound_and_faulty(client):
    sound = client.post("/api/validate", json=SOUND).json()
    assert sound["ok"] is True
    assert sound["graph"]["roots"] == ["A"]
    faulty = client.post("/api/validate", json=FAULTY).json()
    assert faulty["ok"] is False
    assert any(d["severity"] == "error" for d in faulty["diagnostics"])


def test_create_list_get_delete(client):
    created = client.post("/api/designs", json=SOUND).json()
    assert created["ok"] is True and created["valid"] is True and created["created_at"]
    design_id = created["id"]
    assert any(it["id"] == design_id for it in client.get("/api/designs").json())
    assert client.get(f"/api/designs/{design_id}").json()["name"] == "chain"
    assert client.delete(f"/api/designs/{design_id}").status_code == 200
    assert client.get(f"/api/designs/{design_id}").status_code == 404


def test_export_then_import_roundtrips(client):
    design_id = _new(client, SOUND)
    flow = client.get(f"/api/designs/{design_id}/export", params={"format": "flow"}).text
    assert "->" in flow
    imported = client.post("/api/designs/import", files={"file": ("x.flow", flow, "text/plain")}).json()
    assert imported["ok"] is True
    doc = client.get(f"/api/designs/{imported['id']}").json()
    assert [d["name"] for d in doc["departments"]] == ["A", "B", "C"]


def test_simulate_is_gated_on_validity(client):
    assert client.post(f"/api/simulate/{_new(client, FAULTY)}", json={}).status_code == 422
    ok = client.post(f"/api/simulate/{_new(client, SOUND)}", json={"horizon": 5, "dt": 0.1})
    assert ok.status_code == 200
    series = ok.json()
    assert series["names"] == ["A", "B", "C"]
    assert len(series["times"]) > 0 and len(series["backlog"][0]) == 3


def test_analysis(client):
    a = client.get(f"/api/analysis/{_new(client, SOUND)}").json()
    assert abs(sum(a["split"]) - 1.0) < 1e-9
    assert len(a["gaps"]) == 3
    assert client.get(f"/api/analysis/{_new(client, FAULTY)}").status_code == 422


def test_graph_nodes_carry_status(client):
    graph = client.post("/api/validate", json=SOUND).json()["graph"]
    by = {nd["id"]: nd for nd in graph["nodes"]}
    assert by["A"]["is_root"] is True and by["A"]["reachable"] is True
    assert by["A"]["outflow"] == 1.0
    assert all({"status", "outflow", "reachable"} <= set(nd) for nd in graph["nodes"])


def test_reciprocal_cycle_is_valid_with_two_edges(client):
    doc = {
        "name": "cycle", "settings": {"time_per_employee": 1, "headcount": 10},
        "departments": [{"name": "A", "makespan": 1, "demand": 100}, {"name": "B", "makespan": 1}],
        "flows": [{"from": "A", "to": "B", "ratio": 0.9}, {"from": "B", "to": "A", "ratio": 0.4}],
    }
    r = client.post("/api/validate", json=doc).json()
    assert r["ok"] is True
    assert len(r["graph"]["edges"]) == 2


def test_unreachable_department_flagged_in_graph(client):
    doc = {
        "name": "split", "settings": {"time_per_employee": 1},
        "departments": [{"name": n, "makespan": 1} for n in ("A", "B", "C", "D")],
        "flows": [{"from": "A", "to": "B", "ratio": 1.0},
                  {"from": "C", "to": "D", "ratio": 0.5}, {"from": "D", "to": "C", "ratio": 0.5}],
    }
    doc["departments"][0]["demand"] = 10
    by = {nd["id"]: nd for nd in client.post("/api/validate", json=doc).json()["graph"]["nodes"]}
    assert by["C"]["reachable"] is False and by["C"]["status"] == "warn"
    assert by["A"]["reachable"] is True


def test_pages_render(client):
    for path in ["/", "/builder", "/designs"]:
        assert client.get(path).status_code == 200
    design_id = _new(client, SOUND)
    for path in [f"/builder/{design_id}", f"/simulate/{design_id}", f"/analyze/{design_id}"]:
        assert client.get(path).status_code == 200
