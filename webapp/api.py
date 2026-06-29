"""JSON API: validate, CRUD + transfer for designs, gated simulate, and analysis.

Everything computational delegates to ``webapp.adapters`` (which delegates to the engine). The
simulate and analysis endpoints are **gated**: a design that does not validate returns HTTP 422
with its diagnostics instead of running.
"""
from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from staffing_optimizer import dynamics as dyn
from staffing_optimizer import equilibrium as eq
from staffing_optimizer import gaps as gp
from webapp import adapters as A
from webapp import examples_lib
from webapp import store

router = APIRouter(prefix="/api")


@router.get("/examples")
def examples_index():
    return examples_lib.list_examples()


@router.get("/examples/{example_id}")
def example_get(example_id: str):
    doc = examples_lib.load_example(example_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="example not found")
    return doc


def _download_headers(filename: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _load_valid(design_id: str):
    """Load a design and require it to validate; raise 422 with diagnostics otherwise."""
    doc = store.load_design(design_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="design not found")
    net, diags, ok = A.validate_doc(doc)
    if not ok:
        raise HTTPException(
            status_code=422,
            detail={"message": "design must be valid before it can run",
                    "diagnostics": A.diagnostics_json(diags)},
        )
    return doc, net


@router.post("/validate")
def validate(doc: dict = Body(...)):
    _net, diags, ok = A.validate_doc(doc)
    return {"ok": ok, "diagnostics": A.diagnostics_json(diags), "graph": A.graph_json(doc)}


@router.get("/designs")
def list_designs():
    return store.list_designs()


@router.post("/designs")
def create_design(doc: dict = Body(...)):
    _net, diags, ok = A.validate_doc(doc)
    saved = store.save_design({**doc, "valid": ok})
    return {**saved, "ok": ok, "diagnostics": A.diagnostics_json(diags)}


@router.get("/designs/{design_id}")
def get_design(design_id: str):
    doc = store.load_design(design_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="design not found")
    return doc


@router.delete("/designs/{design_id}")
def delete_design(design_id: str):
    if not store.delete_design(design_id):
        raise HTTPException(status_code=404, detail="design not found")
    return {"deleted": design_id}


@router.get("/designs/{design_id}/export")
def export_design(design_id: str, format: str = Query("json", pattern="^(json|flow|yaml)$")):
    doc = store.load_design(design_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="design not found")
    if format == "flow":
        return PlainTextResponse(A.doc_to_flow(doc), headers=_download_headers(f"{design_id}.flow"))
    if format == "yaml":
        return PlainTextResponse(A.doc_to_yaml(doc), headers=_download_headers(f"{design_id}.yaml"))
    return JSONResponse(doc, headers=_download_headers(f"{design_id}.json"))


@router.post("/designs/import")
async def import_design(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8")
    filename = file.filename or "imported"
    name = filename.rsplit(".", 1)[0]
    try:
        if filename.endswith(".flow"):
            doc = A.flow_to_doc(raw, name=name)
        elif filename.endswith((".yaml", ".yml")):
            doc = A.yaml_to_doc(raw, name=name)
        else:
            doc = json.loads(raw)
            doc.setdefault("name", name)
    except Exception as exc:  # noqa: BLE001 - report any parse failure to the user
        raise HTTPException(status_code=400, detail=f"could not import file: {exc}") from exc
    _net, _diags, ok = A.validate_doc(doc)
    saved = store.save_design({**doc, "valid": ok})
    return {**saved, "ok": ok}


@router.get("/analysis/{design_id}")
def analysis(design_id: str):
    _doc, net = _load_valid(design_id)
    return A.analysis_json(net)


@router.post("/simulate/{design_id}")
def simulate(design_id: str, params: dict = Body(default={})):
    _doc, net = _load_valid(design_id)
    scale = float(params.get("scale", 1.0))
    dt = float(params.get("dt", 0.05))
    horizon = float(params.get("horizon", 50.0))
    band = float(params.get("backpressure_band", 0.2))
    if params.get("staffing") == "suggested" and net.headcount:
        base = gp.suggested_allocation(net, net.headcount)
    else:
        base = eq.staffing_requirement(net)
    result = dyn.simulate(net, np.asarray(base) * scale, dt=dt, horizon=horizon, backpressure_band=band)
    return A.result_json(result)
