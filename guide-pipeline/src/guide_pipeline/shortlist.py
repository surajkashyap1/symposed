"""Pick the question before the guide is written (Samarth, 2026-10-18).

After scoring, a review led run stops with the top three questions, each with a
title, a short project brief, its PICO, why it matters, why it is new and its
scope. A person picks one (`python -m guide_pipeline pick <order> <n>`, which
writes the number into the request folder's CHOICE file) and the run is started
again. Only the picked question goes through the final check, so full texts
are only fetched for a question someone wants. If it fails the final check the
run stops again with the shortlist, the failed option marked, for another pick.
The two questions not picked become the guide's swappable alternatives.

Everything factual (counts, PROSPERO dates) comes from the run's API checks.
The model writes only the PICO, the brief and the rationale.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from .alternatives import Alternative, build
from .guide_content import PLAIN_STYLE
from .plain import tidy

SIZE = 3
CHOICE_FILE = "CHOICE"
FAILED_FILE = "failed_checks.json"
SHORTLIST_MD = "SHORTLIST.md"
SHORTLIST_DOCX = "shortlist.docx"

_S = {"type": "string"}
BRIEF_SCHEMA = {"type": "object", "properties": {"brief": _S}, "required": ["brief"],
                "additionalProperties": False}
_BRIEF_SYSTEM = (
    "You write the project brief for one proposed research question, for the person "
    "deciding which question to take on. In two or three sentences say what the project "
    "is, what the team would actually do, and what they would end up with. Use only the "
    "facts given. Describe the project only: do not comment on the numbers, the request, "
    "other possible questions or yourself, and never write in the first person. "
    + PLAIN_STYLE
)


class AwaitingChoice(Exception):
    """The run needs a person to pick a question. Run again once CHOICE is written."""

    def __init__(self, folder: Path, path: Path, options: list[Alternative], note: str = ""):
        self.folder, self.path, self.options, self.note = folder, path, options, note
        super().__init__(f"pick one of {len(options)} questions: see {path}")


def read_choice(folder: Path) -> Optional[int]:
    try:
        text = (Path(folder) / CHOICE_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def write_choice(folder: Path, number: int) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / CHOICE_FILE
    path.write_text(f"{number}\n", encoding="utf-8")
    return path


def failed_checks(folder: Path) -> dict[str, str]:
    """Titles that failed the final check on an earlier pick, with the reason."""
    try:
        return json.loads((Path(folder) / FAILED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_failed(folder: Path, title: str, reason: str) -> None:
    failed = failed_checks(folder)
    failed[title] = reason
    (Path(folder) / FAILED_FILE).write_text(json.dumps(failed, indent=2), encoding="utf-8")
    (Path(folder) / CHOICE_FILE).unlink(missing_ok=True)


def options(scored: list[Any], *, criteria_llm: Any, brief_llm: Any, publication_type: str,
            review_years: int, team: int) -> list[Alternative]:
    """The top questions written up for choosing: PICO, scope, why new, and a brief."""
    out = build([s.assessment for s in scored[:SIZE]], criteria_llm=criteria_llm,
                publication_type=publication_type, review_years=review_years)
    for o in out:
        o.brief = _brief(brief_llm, o, publication_type=publication_type, team=team)
    return out


def _brief(llm: Any, o: Alternative, *, publication_type: str, team: int) -> str:
    pico = "\n".join(f"{k}: {v}" for k, v in o.pico)
    user = (f'Proposed {publication_type}: "{o.title}"\n{pico}\nWhy it matters: {o.rationale}\n'
            f"Size: about {o.eligible_estimate} studies likely to fit, from about "
            f"{o.records_to_screen} search results to screen.\n"
            f"The team: {team} {'person' if team == 1 else 'people'}.")
    try:
        return tidy(str(llm.complete_json(_BRIEF_SYSTEM, user, schema=BRIEF_SCHEMA)["brief"]))
    except Exception:  # noqa: BLE001  a missing brief never blocks the shortlist
        return ""


def alternatives_after(opts: list[Alternative], chosen: int, *, failed: set[str]) -> list[Alternative]:
    """The options not picked (and not failed), renumbered from 1, as the guide's alternatives."""
    rest = [o for o in opts if o.number != chosen and o.title not in failed]
    return [replace(o, number=i) for i, o in enumerate(rest, 1)]


def write(folder: Path, opts: list[Alternative], *, topic: str, key: str,
          failed: dict[str, str], note: str = "") -> Path:
    """SHORTLIST.md (to read or paste) and shortlist.docx (to send)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lines = [f"# Pick a question: {topic}", ""]
    if note:
        lines += [f"**{note}**", ""]
    lines += ["Read the options, pick one, then run:", "",
              f"    python -m guide_pipeline pick {key} <number>", "",
              "and run the batch again. The guide is written for the question picked, and "
              "the other two become its alternatives.", ""]
    for o in opts:
        lines += [f"## Option {o.number}: {o.title}", ""]
        if o.title in failed:
            lines += [f"**Failed the final check, pick another:** {failed[o.title]}", ""]
        if o.brief:
            lines += [f"**Project brief.** {o.brief}", ""]
        lines += ["**PICO**", ""] + [f"- {k}: {v}" for k, v in o.pico] + [""]
        lines += [f"**Why it matters.** {o.rationale}", "", f"**Why it is new.** {o.why_novel}", ""]
        lines += ["**Scope**", ""] + [f"- {k}: {v}" for k, v in o.scope] + [""]
        lines += [f"Best search ({o.search_count} results in PubMed): `{o.search_query}`", ""]
    path = folder / SHORTLIST_MD
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_docx(folder / SHORTLIST_DOCX, opts, topic=topic, failed=failed, note=note)
    return path


def _write_docx(path: Path, opts: list[Alternative], *, topic: str, failed: dict[str, str],
                note: str) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading(f"Pick a question: {topic}", 0)
    if note:
        doc.add_paragraph().add_run(note).bold = True
    doc.add_paragraph("Read the options below and reply with the number you want. We then "
                      "check the chosen question once more against the closest existing "
                      "reviews and write its guide. The other two become your alternatives.")
    for o in opts:
        doc.add_heading(f"Option {o.number}: {o.title}", 1)
        if o.title in failed:
            p = doc.add_paragraph()
            p.add_run("Failed the final check, pick another: ").bold = True
            p.add_run(failed[o.title])
        for label, text in (("Project brief", o.brief), ("Why it matters", o.rationale),
                            ("Why it is new", o.why_novel)):
            if text:
                p = doc.add_paragraph()
                p.add_run(f"{label}. ").bold = True
                p.add_run(text)
        for heading, rows in (("PICO", o.pico), ("Scope", o.scope)):
            if not rows:
                continue
            doc.add_heading(heading, 2)
            table = doc.add_table(rows=0, cols=2)
            table.style = "Light Grid Accent 1"
            for k, v in rows:
                cells = table.add_row().cells
                cells[0].text, cells[1].text = k, v
    doc.save(str(path))
