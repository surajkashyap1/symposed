"""One guide request, end to end, plus the metrics that let us improve the pipeline.

Stages: PROSPERO freshness check -> landscape -> candidates and gates (stages 2-4)
-> criteria for the chosen question -> retrieval -> full-recall screening -> the
guide. If nothing fits the user's stated requirements, the run stops with the
reason to email them (needs_contact) and still records its metrics.

Every run appends one line to `<output_dir>/metrics.jsonl`: what was asked, how
each gate behaved, what was found, and what it cost and how long it took. That
is the feedback loop for tuning cost and quality over time — e.g. whether blank
topic requests are cheaper than specific ones.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .candidates import (
    FILTER_PRIMARY,
    FOUND_OTHER_TYPE,
    NEEDS_CONTACT,
    ScreenResult,
    screen_candidates,
)
from .gates import SYSTEMATIC, records_cap
from .guide import build_guide
from .landscape import Landscape, assess_landscape
from .llm import LLMClient, UsageMeter
from .prospero import ProsperoMirror
from .request import GuideRequest
from .retrieval import RetrievalResult, retrieve
from .screening import STATUSES, ScreeningResult, screen_papers, write_criteria
from .settings import Settings
from .sources import Sources
from .workspace import Workspace, create_workspace

Progress = Callable[[str], None]


def _git_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
            check=True, cwd=Path(__file__).parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


@dataclass
class RunReport:
    request: GuideRequest
    outcome: str
    workspace: Workspace
    screen: ScreenResult
    title: str = ""
    publication_type: str = ""
    landscape: Optional[Landscape] = None
    retrieval: Optional[RetrievalResult] = None
    screening: Optional[ScreeningResult] = None
    guide_path: str = ""
    seconds: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


def _gate_counts(screen: ScreenResult) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter] = {}
    for a in screen.assessments:
        for g in a.verdict.gates:
            counts.setdefault(g.name, Counter())[g.outcome] += 1
    return {name: dict(c) for name, c in counts.items()}


def build_metrics(report: RunReport, meter: UsageMeter, settings: Settings) -> dict[str, Any]:
    """The per-guide feedback record (flat enough to load into a spreadsheet)."""
    r, prefs, s = report.request, report.request.preferences, report.screen
    top = s.top
    screened = report.screening
    n_screened = len(screened.papers) if screened else 0
    cost_screening = sum(meter.by_task.get(t, 0.0) for t in
                         ("attribute_extraction", "screening", "outcome_grouping"))
    return {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline_version": _git_version(),
        "order_id": r.order_id,
        # the request
        "publication_type_requested": prefs.publication_type,
        "type_flexible": prefs.type_flexible,
        "topic_given": not r.blank_topic,
        "topic_flexibility": prefs.topic_flexibility,
        "specialty_count": len(prefs.specialties),
        "team_size": prefs.collaborators,
        # stages 2-4: candidates and gates
        "outcome": report.outcome,
        "batches": s.batches,
        "candidates_generated": len(s.assessments),
        "candidates_passed": len(s.survivors),
        "candidates_downgraded": len(s.downgraded),
        "pass_rate": round(len(s.survivors) / len(s.assessments), 3) if s.assessments else 0.0,
        "gate_outcomes": _gate_counts(s),
        "axes_tried": sorted({a.candidate.axis for a in s.assessments}),
        "chosen_axis": top.candidate.axis if top else None,
        "chosen_eligible_studies": top.counts.eligible_studies if top else None,
        "chosen_records_to_screen": top.counts.records_to_screen if top else None,
        "chosen_prospero_top_score": (
            top.prospero.matches[0].score if top and top.prospero.matches else 0.0
        ),
        "publication_type_delivered": report.publication_type or None,
        # stage 5: retrieval and screening
        "papers_retrieved": len(report.retrieval.papers) if report.retrieval else 0,
        "papers_screened": n_screened,
        "full_text_share": round(screened.full_text_screened / n_screened, 3) if n_screened else 0.0,
        "status_counts": screened.counts if screened else {},
        "own_access_list": len(screened.unclear_without_open_access()) if screened else 0,
        "distinct_primary_outcomes": (
            screened.heterogeneity.distinct_outcomes
            if screened and screened.heterogeneity else None
        ),
        "heterogeneity_flag": (
            screened.heterogeneity.flagged if screened and screened.heterogeneity else None
        ),
        # cost and time
        "cost_usd": round(meter.cost_usd, 4),
        "cost_by_task_usd": {k: round(v, 4) for k, v in sorted(meter.by_task.items())},
        "cost_candidates_usd": round(meter.by_task.get("candidate_generation", 0.0), 4),
        "cost_screening_usd": round(cost_screening, 4),
        "cost_per_screened_paper_usd": round(cost_screening / n_screened, 5) if n_screened else None,
        "model_calls": meter.calls,
        "input_tokens": meter.input_tokens,
        "output_tokens": meter.output_tokens,
        "cache_read_tokens": meter.cache_read_tokens,
        "seconds_by_stage": {k: round(v, 1) for k, v in report.seconds.items()},
        "seconds_total": round(sum(report.seconds.values()), 1),
    }


def run_request(
    request: GuideRequest,
    *,
    settings: Settings,
    sources: Sources,
    mirror: ProsperoMirror,
    llms: dict[str, LLMClient],
    meter: UsageMeter,
    limit: Optional[int] = None,
    progress: Optional[Progress] = None,
) -> RunReport:
    say = progress or (lambda _m: None)
    th = settings.thresholds
    prefs = request.preferences
    seconds: dict[str, float] = {}

    def timed(stage: str, fn: Callable[[], Any]) -> Any:
        start = time.monotonic()
        try:
            return fn()
        finally:
            seconds[stage] = seconds.get(stage, 0.0) + time.monotonic() - start

    mirror.ensure_fresh(max_age_days=settings.prospero_max_age_days)
    say(f"Landscape for: {request.search_topic}")
    landscape = timed("landscape", lambda: assess_landscape(
        sources.pubmed, request.search_topic, years=settings.landscape_years))

    say("Generating and gating candidate questions...")
    screen = timed("candidates", lambda: screen_candidates(
        llms["candidate_generation"], sources.pubmed, sources.clinicaltrials, mirror,
        request.generation_topic, th, landscape=landscape,
        mirror_max_age_days=settings.prospero_max_age_days, preferences=prefs,
    ))
    label = request.order_id or "request"
    workspace = create_workspace(
        screen.top.candidate.title if screen.top else f"{label} needs contact",
        base=settings.output_dir,
    )
    report = RunReport(request, screen.outcome, workspace, screen, landscape=landscape,
                       seconds=seconds)

    if screen.outcome == NEEDS_CONTACT or screen.top is None:
        say(f"Nothing fits the stated requirements: {screen.contact_reason}")
        _finish(report, meter, settings, extra={"contact_reason": screen.contact_reason})
        return report

    top = screen.top
    report.title = top.candidate.title
    report.publication_type = (
        "scoping or narrative review" if screen.outcome == FOUND_OTHER_TYPE
        else prefs.publication_type
    )
    say(f"Chosen question ({top.candidate.axis}): {report.title}")

    criteria = timed("criteria", lambda: write_criteria(
        llms["criteria_writing"], report.title, publication_type=report.publication_type))
    query = top.candidate.pubmed_query
    if report.publication_type == SYSTEMATIC:
        query = f"({query}) {FILTER_PRIMARY}"
    retrieval = timed("retrieval", lambda: retrieve(
        sources.pubmed, query, max_records=records_cap(th, collaborators=prefs.collaborators)))
    report.retrieval = retrieval
    papers = retrieval.papers[:limit] if limit else retrieval.papers
    say(f"Screening {len(papers)} of {len(retrieval.papers)} papers "
        f"({settings.llm_concurrency} at a time)...")
    screening = timed("screening", lambda: screen_papers(
        llms["attribute_extraction"], llms["screening"], criteria, papers,
        europepmc=sources.europepmc, grouping_llm=llms["outcome_grouping"],
        heterogeneity_threshold=th.heterogeneity_max_outcomes,
        fulltext_max_chars=settings.fulltext_max_chars,
        concurrency=settings.llm_concurrency,
    ))
    report.screening = screening
    search_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report.guide_path = timed("guide", lambda: build_guide(
        workspace, report.title, retrieval, screening,
        search_date=search_date, landscape=landscape))
    _finish(report, meter, settings, extra={
        "search_date": search_date,
        "title": report.title,
        "axis": top.candidate.axis,
        "rationale": top.candidate.rationale,
        "gates": [g.__dict__ for g in top.verdict.gates],
        "prospero_check": top.prospero.as_dict(),
        "searches_run": [s.__dict__ for s in top.searches],
        **retrieval.as_dict(),
        **screening.as_dict(),
    })
    return report


def _finish(report: RunReport, meter: UsageMeter, settings: Settings, *, extra: dict) -> None:
    report.metrics = build_metrics(report, meter, settings)
    report.workspace.write_results({
        "order_id": report.request.order_id,
        "outcome": report.outcome,
        "publication_type": report.publication_type,
        "candidates": [
            {"title": a.candidate.title, "axis": a.candidate.axis, "batch": a.batch,
             "outcome": a.verdict.outcome, "reasons": a.verdict.reasons,
             "eligible_studies": a.counts.eligible_studies,
             "recent_reviews": a.counts.recent_reviews}
            for a in report.screen.assessments
        ],
        **extra,
        "metrics": report.metrics,
    })
    path = Path(settings.output_dir) / "metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report.metrics) + "\n")


def summarise_metrics(path: str | Path) -> dict[str, Any]:
    """Averages across runs, split by whether a topic was given."""
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

    def mean(values: list[float]) -> Optional[float]:
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    out: dict[str, Any] = {"runs": len(rows)}
    for label, group in (("topic_given", [r for r in rows if r.get("topic_given")]),
                         ("blank_topic", [r for r in rows if not r.get("topic_given")])):
        out[label] = {
            "runs": len(group),
            "found_rate": mean([1.0 if r["outcome"] != NEEDS_CONTACT else 0.0 for r in group]),
            "mean_cost_usd": mean([r["cost_usd"] for r in group]),
            "mean_cost_candidates_usd": mean([r["cost_candidates_usd"] for r in group]),
            "mean_cost_per_paper_usd": mean([r["cost_per_screened_paper_usd"] for r in group]),
            "mean_batches": mean([r["batches"] for r in group]),
            "mean_pass_rate": mean([r["pass_rate"] for r in group]),
            "mean_seconds": mean([r["seconds_total"] for r in group]),
        }
    return out
