"""Per-request output folder.

Each guide request gets its own folder holding a JSON of everything found
(`results.json`), the draft Word document (`guide.docx`), and a `cache/` of raw
API responses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "request"


@dataclass(frozen=True)
class Workspace:
    """One output folder per guide request."""

    dir: Path

    @property
    def results_path(self) -> Path:
        return self.dir / "results.json"

    @property
    def guide_path(self) -> Path:
        return self.dir / "guide.docx"

    @property
    def cache_dir(self) -> Path:
        return self.dir / "cache"

    def write_results(self, data: Any) -> Path:
        self.results_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.results_path


def create_workspace(
    topic: str = "",
    *,
    base: str | Path = "output",
    request_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Workspace:
    """Create and return the folder for one request (idempotent for a given name)."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    name = request_id or f"{stamp}_{slugify(topic)}"
    directory = Path(base) / name
    (directory / "cache").mkdir(parents=True, exist_ok=True)
    return Workspace(dir=directory)
