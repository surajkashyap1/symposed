"""Write every deliverable for one guide into its workspace.

  guide_model.json     the render model (re-render with `render <folder>`)
  screenshots/         PubMed screenshots of each numbered search strategy
  guide.pdf            the designed guide
  tracker.xlsx, protocol.docx, prospero_draft.docx   the editable companions
  guide-pack.zip       all of the customer files in one archive, for review
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable

from .companions import write_all
from .guide_pdf import write_pdf
from .screenshots import capture_searches
from .workspace import Workspace

PACK_FILES = ("guide.pdf", "tracker.xlsx", "protocol.docx", "prospero_draft.docx")


def build_outputs(workspace: Workspace, model: dict[str, Any], *, screenshots: bool = True,
                  say: Callable[[str], None] = print) -> dict[str, Path]:
    d = workspace.dir
    if screenshots:
        model["screenshots"] = capture_searches(model, d / "screenshots", say=say)
    workspace.model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    out: dict[str, Path] = {"pdf": write_pdf(model, workspace.guide_path)}
    out.update(write_all(model, d))
    pack = d / "guide-pack.zip"
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        for name in PACK_FILES:
            if (d / name).exists():
                z.write(d / name, arcname=name)
    out["pack"] = pack
    return out


def rerender(directory: str | Path, *, screenshots: bool = False,
             say: Callable[[str], None] = print) -> dict[str, Path]:
    """Rebuild the PDF and companions from a saved guide_model.json (no model calls)."""
    ws = Workspace(Path(directory))
    model = json.loads(ws.model_path.read_text(encoding="utf-8"))
    return build_outputs(ws, model, screenshots=screenshots, say=say)
