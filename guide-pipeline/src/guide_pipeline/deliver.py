"""Write every deliverable for one guide into its workspace.

  guide_model.json     the render model (re-render with `render <folder>`)
  screenshots/         PubMed screenshots of each numbered search strategy
  guide.docx           the designed guide, read-only (guide_docx.py)
  guide.pdf            a PDF copy of it, only with GUIDE_PDF=1
  tracker.xlsx, protocol.docx, prospero_draft.docx   the editable companions
  guide-pack.zip       all of the customer files in one archive, for review
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from .companions import write_all
from .guide_docx import write_docx
from .screenshots import capture_searches
from .workspace import Workspace

PACK_FILES = ("guide.docx", "guide.pdf", "tracker.xlsx", "protocol.docx", "prospero_draft.docx")


def build_outputs(workspace: Workspace, model: dict[str, Any], *, screenshots: bool = True,
                  say: Callable[[str], None] = print, password: Optional[str] = None,
                  pdf: Optional[bool] = None) -> dict[str, Any]:
    """`password` and `pdf` default to GUIDE_PASSWORD and GUIDE_PDF in the settings.
    `warnings` in the result lists anything the reviewer should check in the guide."""
    if password is None or pdf is None:
        from .settings import Settings

        settings = Settings.load()
        password = settings.guide_password if password is None else password
        pdf = settings.guide_pdf if pdf is None else pdf
    d = workspace.dir
    if screenshots:
        model["screenshots"] = capture_searches(model, d / "screenshots", say=say)
    workspace.model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False, default=str),
                                    encoding="utf-8")
    workspace.pdf_path.unlink(missing_ok=True)  # never ship a PDF of an older version
    warnings = write_docx(model, workspace.guide_path, password=password,
                          pdf_path=workspace.pdf_path if pdf else None, say=say)
    out: dict[str, Any] = {"guide": workspace.guide_path}
    if workspace.pdf_path.exists():
        out["pdf"] = workspace.pdf_path
    out.update(write_all(model, d))
    pack = d / "guide-pack.zip"
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        for name in PACK_FILES:
            if (d / name).exists():
                z.write(d / name, arcname=name)
    out["pack"] = pack
    out["warnings"] = warnings
    return out


def rerender(directory: str | Path, *, screenshots: bool = False,
             say: Callable[[str], None] = print) -> dict[str, Any]:
    """Rebuild the guide and companions from a saved guide_model.json (no model calls)."""
    ws = Workspace(Path(directory))
    model = json.loads(ws.model_path.read_text(encoding="utf-8"))
    return build_outputs(ws, model, screenshots=screenshots, say=say)
