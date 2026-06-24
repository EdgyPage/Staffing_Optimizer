"""File persistence for design documents.

Designs are saved as timestamped JSON files in ``designs/`` (``<timestamp>_<slug>.json``).
The timestamp is both in the filename (the id) and in the document's ``created_at`` field, so
systems are easy to find, sort, and transfer. No database.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

DESIGNS_DIR = Path(__file__).resolve().parents[1] / "designs"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _slug(name: str | None) -> str:
    return _SLUG_RE.sub("-", (name or "design").lower()).strip("-") or "design"


def _path_for(design_id: str) -> Path | None:
    """Resolve a design id to a path inside DESIGNS_DIR, or None if it escapes (path traversal)."""
    if not design_id or not _ID_RE.match(design_id):
        return None
    path = (DESIGNS_DIR / f"{design_id}.json").resolve()
    if path.parent != DESIGNS_DIR.resolve():
        return None
    return path


def _summary(design_id: str, doc: dict) -> dict:
    return {
        "id": design_id,
        "name": doc.get("name"),
        "created_at": doc.get("created_at"),
        "valid": doc.get("valid"),
    }


def save_design(doc: dict) -> dict:
    """Persist a design with a fresh timestamp; returns its summary (id, name, created_at, valid)."""
    DESIGNS_DIR.mkdir(parents=True, exist_ok=True)
    created = datetime.now().isoformat(timespec="seconds")
    doc = {**doc, "created_at": created}
    stamp = re.sub(r"[^0-9T]", "", created)  # 2026-06-24T15:30:00 -> 20260624T153000
    design_id = f"{stamp}_{_slug(doc.get('name'))}"
    (DESIGNS_DIR / f"{design_id}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return _summary(design_id, doc)


def list_designs() -> list[dict]:
    """Summaries of all saved designs, newest first."""
    if not DESIGNS_DIR.exists():
        return []
    out = []
    for path in sorted(DESIGNS_DIR.glob("*.json"), reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(_summary(path.stem, doc))
    return out


def load_design(design_id: str) -> dict | None:
    path = _path_for(design_id)
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_design(design_id: str) -> bool:
    path = _path_for(design_id)
    if path is None or not path.exists():
        return False
    path.unlink()
    return True
