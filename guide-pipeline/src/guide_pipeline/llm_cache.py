"""Replayable model calls, so a paused run can resume without paying twice.

Review led discovery stops when it needs full texts a person has to fetch
(`discovery.AwaitingFullTexts`). Running the request again replays it from the
start: API responses already come from the on-disk HTTP cache, and this wrapper
does the same for model replies, keyed on the exact request. Every step before
the pause is therefore free and identical the second time, and the run carries
on from where it stopped.

Only `complete_json` is cached. Batch calls (`complete_json_many`, used for
per-paper screening after every pause) pass straight through.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


class CachedLLM:
    def __init__(self, inner: Any, folder: Path, *, task: str = ""):
        self.inner, self.folder, self.task = inner, Path(folder), task
        self.folder.mkdir(parents=True, exist_ok=True)
        self.hits = 0

    def _key(self, system: str, user: str, schema: Optional[dict]) -> str:
        model = getattr(self.inner, "model", "")
        effort = getattr(self.inner, "effort", "")
        raw = json.dumps([model, effort, system, user, schema], sort_keys=True,
                         ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def complete_json(self, system: str, user: str, *, schema: Optional[dict] = None,
                      cache_system: bool = False) -> dict[str, Any]:
        path = self.folder / f"{self.task or 'llm'}-{self._key(system, user, schema)[:24]}.json"
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        data = self.inner.complete_json(system, user, schema=schema, cache_system=cache_system)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def __getattr__(self, name: str) -> Any:  # complete_json_many, model, effort, ...
        return getattr(self.inner, name)


def cached(llms: dict[str, Any], folder: Path) -> dict[str, Any]:
    return {task: CachedLLM(llm, folder, task=task) for task, llm in llms.items()}
