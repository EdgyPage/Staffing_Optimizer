"""FastAPI app: serves the HTML pages and mounts the JSON API and static assets."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp import adapters as A
from webapp import store
from webapp.api import router

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def seed_examples() -> None:
    """On first run (empty store), import the bundled example so there is something to open."""
    if store.list_designs():
        return
    example = BASE.parent / "examples" / "warehouse_5dept.flow"
    if not example.exists():
        return
    doc = A.flow_to_doc(example.read_text(encoding="utf-8"), name="warehouse_5dept")
    _net, _diags, ok = A.validate_doc(doc)
    store.save_design({**doc, "valid": ok})


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_examples()
    yield


app = FastAPI(title="Staffing Optimizer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.include_router(router)


def _page(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx)


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/builder")


@app.get("/builder", response_class=HTMLResponse)
def builder(request: Request):
    return _page(request, "builder.html", design_id=None, active="builder")


@app.get("/builder/{design_id}", response_class=HTMLResponse)
def builder_edit(request: Request, design_id: str):
    return _page(request, "builder.html", design_id=design_id, active="builder")


@app.get("/designs", response_class=HTMLResponse)
def designs_page(request: Request):
    return _page(request, "designs.html", active="designs")


@app.get("/simulate/{design_id}", response_class=HTMLResponse)
def simulate_page(request: Request, design_id: str):
    return _page(request, "simulate.html", design_id=design_id, active="simulate")


@app.get("/analyze/{design_id}", response_class=HTMLResponse)
def analyze_page(request: Request, design_id: str):
    return _page(request, "analyze.html", design_id=design_id, active="analyze")
