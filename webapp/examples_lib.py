"""Read-only access to the bundled example designs in ``webapp/examples/*.json``.

These are curated, versioned design documents (each with a ``description``) that returning or
non-technical users can open as a copy in the builder. They are never written to.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def list_examples() -> list[dict]:
    """Summaries (id, name, description) of the bundled examples, in filename order."""
    out = []
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({"id": path.stem, "name": doc.get("name", path.stem),
                    "description": doc.get("description", "")})
    return out


def load_example(example_id: str) -> dict | None:
    if not example_id or not _ID_RE.match(example_id):
        return None
    path = (EXAMPLES_DIR / f"{example_id}.json").resolve()
    if path.parent != EXAMPLES_DIR.resolve() or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
