"""FastAPI app: serves the HTML pages and mounts the JSON API and static assets."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp.api import router

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="Staffing Optimizer")
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


@app.get("/examples", response_class=HTMLResponse)
def examples_page(request: Request):
    return _page(request, "examples.html", active="examples")


@app.get("/help", response_class=HTMLResponse)
def help_page(request: Request):
    return _page(request, "help.html", active="help")
