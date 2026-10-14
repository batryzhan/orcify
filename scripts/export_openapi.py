"""Regenerate the committed FastAPI OpenAPI document."""

from __future__ import annotations

import json
from pathlib import Path

from services.api.app.http import app

destination = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"
destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {destination}")
