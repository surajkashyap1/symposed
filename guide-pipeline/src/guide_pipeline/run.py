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
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from . import alternatives as alt_mod
from . import novelty, shortlist
from .candidates import (
    FILTER_PRIMARY,
    FOUND,
    FOUND_OTHER_TYPE,
    NEEDS_CONTACT,
    Candidate,
    ScreenResult,
    assess_candidate,
    screen_candidates,
)
from .deliver import build_outputs
from .gates import SYSTEMATIC, records_cap
from .discovery import Discovery, FinalCheck, FullTextStore, discover, final_check
from .guide_content import assemble
from .guide_model import build_model
from .landscape import Landscape, assess_landscape
from .llm import LLMClient, UsageMeter
from .plain import tidy
from .prospero import ProsperoMirror
from .request import GuideRequest
from .retrieval import RetrievalResult, retrieve
from .screening import (
    LIKELY_ELIGIBLE,
    STATUSES,
    UNCLEAR,
    ScreeningResult,
    screen_papers,
    write_criteria,
)
from .scoring import (
    ScoreWeights,
    Selection,
    break_tie,
    rank,
    rescore,
    score_candidate,
    tied_leaders,
)
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
    workspace: Optional[Workspace]  # created once the chosen question is known
    screen: ScreenResult
    title: str = ""
    publication_type: str = ""
    landscape: Optional[Landscape] = None
    retrieval: Optional[RetrievalResult] = None
    screening: Optional[ScreeningResult] = None
    guide_path: str = ""
    pack_path: str = ""  # zip of the PDF and companion files
    discovery: Optional[Discovery] = None  # review led discovery (guide v2)
    final_checks: list[FinalCheck] = field(default_factory=list)
    novelty_checks: list[Any] = field(default_factory=list)
    alternatives: list[alt_mod.Alternative] = field(default_factory=list)
    swap: bool = False  # a re-run on an alternative the user chose
    seconds: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    selection: Optional[Selection] = None
    content: Any = None  # GuideContent, once the guide is written


def _gate_counts(screen: ScreenResult) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter] = {}
    for a in screen.assessments:
        for g in a.verdict.gates:
            counts.setdefault(g.name, Counter())[g.outcome] += 1
    return {name: dict(c) for name, c in counts.items()}


def _discovery_metrics(report: RunReport, settings: Settings) -> dict[str, Any]:
    d = report.discovery
    if d is None:
        return {"discovery_mode": "axes"}
    readings = [r for t in d.trials for r in t.readings] + [
        r for c in report.final_checks for r in c.readings]
    return {
        "discovery_mode": "reviews",
        "topics_considered": len(d.topics),
        "topics_tried": len(d.trials),
        "topic_routes": [t.route for t in d.trials],
        "reviews_read": len(readings),
        "reviews_supplied": sum(r.basis.startswith("full text (supplied") for r in readings),
        "reviews_open_access": sum("open access" in r.basis for r in readings),
        "reviews_abstract_only": sum(r.basis == "abstract only" for r in readings),
        "final_checks": len(report.final_checks),
        "final_checks_failed": sum(not c.passed for c in report.final_checks),
    }


def build_metrics(report: RunReport, meter: UsageMeter, settings: Settings) -> dict[str, Any]:
    """The per-guide feedback record (flat enough to load into a spreadsheet)."""
    r, prefs, s = report.request, report.request.preferences, report.screen
    sel = report.selection
    top = sel.winner.assessment if sel and sel.winner else s.top
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
        **_discovery_metrics(report, settings),
        "chosen_eligible_studies": top.counts.eligible_studies if top else None,
        "chosen_records_to_screen": top.counts.records_to_screen if top else None,
        "chosen_prospero_top_score": (
            top.prospero.matches[0].score if top and top.prospero.matches else 0.0
        ),
        "publication_type_delivered": report.publication_type or None,
        "tied_candidates": len(report.selection.tied) if report.selection else 0,
        "tie_break_used": bool(report.selection and report.selection.tie_break),
        "guide_warnings": len(report.content.warnings) if report.content else None,
        "strategy_counts": ([st.count for st in report.content.strategies["strategies"]]
                            if report.content else None),
        "winner_score": report.selection.winner.total if report.selection and report.selection.winner else None,
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
        # finding the question: axis generation plus review led discovery
        "cost_candidates_usd": round(sum(meter.by_task.get(t, 0.0) for t in (
            "candidate_generation", "topic_generation", "review_reading", "gap_candidates",
            "axis_lens", "final_check", "novelty_check", "shortlist_brief")), 4),
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
    avoid_titles: tuple[str, ...] = (),
    screenshots: bool = True,
    store: Optional[FullTextStore] = None,
    forced: Optional[Candidate] = None,
    choose_dir: Optional[Path] = None,
) -> RunReport:
    """One request end to end.

    With `settings.discovery_mode == "reviews"` and a `store`, candidates come
    from the gaps in the closest existing reviews and the chosen question gets a
    final check against the reviews nearest to it. Either may raise
    `discovery.AwaitingFullTexts`; run the request again once the files are in.

    `forced` is a swap: the user chose one of their alternatives. Its novelty
    checks (gates, PROSPERO) are re-run today, and if it still passes the full
    guide is written for it, with no new alternatives.

    `choose_dir` (review led runs) makes the run stop after scoring with a
    shortlist of the top questions (`shortlist.AwaitingChoice`) until a person
    picks one. Only the picked question gets the final check.
    """
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
        sources.pubmed, request.search_topic, years=settings.landscape_years,
        openalex=getattr(sources, "openalex", None)))

    discovery: Optional[Discovery] = None
    if forced is not None:
        say(f"Swap: re-checking {forced.title!r} before writing its guide")
        a = timed("candidates", lambda: assess_candidate(
            sources.pubmed, sources.clinicaltrials, mirror, forced, th,
            mirror_max_age_days=settings.prospero_max_age_days,
            publication_type=prefs.publication_type, collaborators=prefs.collaborators))
        ok = a.verdict.passed
        screen = ScreenResult([a], [a] if ok else [], a if ok else None, batches=1,
                              outcome=FOUND if ok else NEEDS_CONTACT,
                              contact_reason="" if ok else
                              "the alternative no longer passes our checks: "
                              + "; ".join(a.verdict.reasons))
    elif settings.discovery_mode == "reviews" and store is not None:
        say("Finding topics and the closest existing reviews...")
        discovery = timed("candidates", lambda: discover(
            llms=llms, pubmed=sources.pubmed, clinicaltrials=sources.clinicaltrials,
            mirror=mirror, store=store, stated_topic=request.topic, prefs=prefs, th=th,
            landscape=landscape, mirror_max_age_days=settings.prospero_max_age_days,
            avoid_titles=tuple(avoid_titles), say=say))
        screen = discovery.screen
    else:
        say("Generating and gating candidate questions...")
        screen = timed("candidates", lambda: screen_candidates(
            llms["candidate_generation"], sources.pubmed, sources.clinicaltrials, mirror,
            request.generation_topic, th, landscape=landscape,
            mirror_max_age_days=settings.prospero_max_age_days, preferences=prefs,
            avoid_titles=tuple(avoid_titles),
        ))
    label = request.order_id or "request"
    report = RunReport(request, screen.outcome, None, screen, landscape=landscape,
                       seconds=seconds, discovery=discovery)

    if screen.outcome == NEEDS_CONTACT or screen.top is None:
        say(f"Nothing fits the stated requirements: {screen.contact_reason}")
        report.workspace = create_workspace(f"{label} needs contact", base=settings.output_dir)
        _finish(report, meter, settings, extra={
            "contact_reason": screen.contact_reason,
            "discovery": discovery.as_dict() if discovery else None})
        return report

    report.publication_type = (
        "scoping or narrative review" if screen.outcome == FOUND_OTHER_TYPE
        else prefs.publication_type
    )
    pool = screen.survivors if screen.outcome != FOUND_OTHER_TYPE else screen.downgraded
    cap = records_cap(th, collaborators=prefs.collaborators)
    today = datetime.now(timezone.utc).date()
    weights = ScoreWeights.from_env()

    def recent_share(a) -> float:
        # One extra count: how much of the eligible evidence is recent.
        q = f"({a.candidate.pubmed_query}) {FILTER_PRIMARY}"
        recent = sources.pubmed.count(q, min_year=today.year - th.recency_years + 1)
        return recent / a.counts.eligible_studies if a.counts.eligible_studies else 0.0

    score_kw = dict(preferences=prefs, topic=request.topic, thresholds=th, weights=weights)
    shares = timed("scoring", lambda: {a.candidate.title: recent_share(a) for a in pool})
    initial = rank([score_candidate(a, recent_share=shares[a.candidate.title], **score_kw)
                    for a in pool])
    tied = tied_leaders(initial, margin=th.score_margin, max_tied=th.max_tied)
    picked_alternatives: Optional[list[alt_mod.Alternative]] = None
    if discovery is not None and forced is None and choose_dir is not None:
        # Every question is judged for novelty the way a journal editor would, best
        # score first, until three pass. Then a person picks before anything else
        # is spent.
        say("Checking each question for novelty against the closest papers...")
        top_scored, checks = timed("novelty", lambda: novelty.screen(
            initial, llm=llms["novelty_check"], pubmed=sources.pubmed, th=th,
            publication_type=report.publication_type, context=prefs.context,
            want=shortlist.SIZE, say=say))
        report.novelty_checks = checks
        if not top_scored:
            reason = "no question passed the novelty check: " + "; ".join(
                f"{c.title}: {c.verdict}, {c.editor_view}" for c in checks)
            say(reason)
            report.outcome = NEEDS_CONTACT
            report.screen = replace(screen, outcome=NEEDS_CONTACT, contact_reason=reason)
            report.workspace = create_workspace(f"{label} needs contact", base=settings.output_dir)
            _finish(report, meter, settings, extra={
                "contact_reason": reason, "discovery": discovery.as_dict(),
                "novelty_checks": [c.as_dict() for c in checks]})
            return report
        say(f"Writing up the top {len(top_scored)} questions to pick from...")
        opts = timed("shortlist", lambda: shortlist.options(
            top_scored, criteria_llm=llms["criteria_writing"],
            brief_llm=llms["shortlist_brief"], publication_type=report.publication_type,
            review_years=th.review_years, team=prefs.collaborators))
        by_title = {c.title: c for c in checks}
        for o in opts:
            o.novelty = by_title[o.title].as_dict() if o.title in by_title else {}
        topic = request.topic or request.search_topic
        failed = shortlist.failed_checks(choose_dir)

        def ask(note: str = "") -> shortlist.AwaitingChoice:
            path = shortlist.write(choose_dir, opts, topic=topic, key=choose_dir.name,
                                   failed=failed, note=note)
            return shortlist.AwaitingChoice(choose_dir, path, opts, note)

        n = shortlist.read_choice(choose_dir)
        if n is None or not 1 <= n <= len(opts) or opts[n - 1].title in failed:
            raise ask()
        chosen = top_scored[n - 1]
        say(f"Final check on option {n}: {chosen.assessment.candidate.title}")
        check = timed("final_check", lambda: final_check(
            llms=llms, pubmed=sources.pubmed, store=store, assessment=chosen.assessment,
            prefs=prefs, th=th, say=say))
        report.final_checks.append(check)
        if not check.passed:
            reason = check.suggested_change or "; ".join(
                f"{k}: {v}" for k, v in check.reasons.items())
            shortlist.record_failed(choose_dir, check.title, tidy(reason))
            failed = shortlist.failed_checks(choose_dir)
            if any(o.title not in failed for o in opts):
                raise ask(f"Option {n} failed the final check. Please pick another.")
            reason = "every shortlisted question failed the final check: " + "; ".join(
                f"{t}: {r}" for t, r in failed.items())
            say(reason)
            report.outcome = NEEDS_CONTACT
            report.screen = replace(screen, outcome=NEEDS_CONTACT, contact_reason=reason)
            report.workspace = create_workspace(f"{label} needs contact", base=settings.output_dir)
            _finish(report, meter, settings, extra={
                "contact_reason": reason, "discovery": discovery.as_dict(),
                "final_checks": [c.as_dict() for c in report.final_checks]})
            return report
        tied = [chosen]
        picked_alternatives = shortlist.alternatives_after(opts, n, failed=set(failed))
    elif discovery is not None and forced is None:
        # Final check, best score first: read the reviews closest to the title and
        # ask whether it is new, publishable and realistic. The first to pass goes on.
        chosen = None
        for s in initial:
            say(f"Final check: {s.assessment.candidate.title}")
            check = timed("final_check", lambda: final_check(
                llms=llms, pubmed=sources.pubmed, store=store, assessment=s.assessment,
                prefs=prefs, th=th, say=say))
            report.final_checks.append(check)
            if check.passed:
                chosen = s
                break
        if chosen is None:
            reason = "every surviving question failed the final check: " + "; ".join(
                f"{c.title}: {c.suggested_change or 'see reasons'}" for c in report.final_checks)
            say(reason)
            report.outcome = NEEDS_CONTACT
            report.screen = replace(screen, outcome=NEEDS_CONTACT, contact_reason=reason)
            report.workspace = create_workspace(f"{label} needs contact", base=settings.output_dir)
            _finish(report, meter, settings, extra={
                "contact_reason": reason, "discovery": discovery.as_dict(),
                "final_checks": [c.as_dict() for c in report.final_checks]})
            return report
        tied = [chosen]
    selection = Selection(initial=initial, tied=tied)
    if len(tied) > 1:
        say(f"{len(tied)} candidates within {th.score_margin} of each other: "
            "deep retrieval for each")

    deep: dict[str, tuple] = {}
    for s in tied:  # Stage 5: deep retrieval for the winner, or for every tied one
        a = s.assessment
        say(f"Deep retrieval ({a.candidate.axis}): {a.candidate.title}")
        criteria = timed("criteria", lambda: write_criteria(
            llms["criteria_writing"], a.candidate.title,
            publication_type=report.publication_type))
        query = a.candidate.pubmed_query
        if report.publication_type == SYSTEMATIC:
            query = f"({query}) {FILTER_PRIMARY}"
        retrieval = timed("retrieval", lambda: retrieve(
            sources.pubmed, query, max_records=cap, europepmc=sources.europepmc,
            concept_query=a.candidate.pubmed_query, max_preprints=th.max_preprints))
        papers = retrieval.papers[:limit] if limit else retrieval.papers
        say(f"  screening {len(papers)} of {len(retrieval.papers)} papers...")
        screening = timed("screening", lambda: screen_papers(
            llms["attribute_extraction"], llms["screening"], criteria, papers,
            europepmc=sources.europepmc, grouping_llm=llms["outcome_grouping"],
            heterogeneity_threshold=th.heterogeneity_max_outcomes,
            fulltext_max_chars=settings.fulltext_max_chars,
            concurrency=settings.llm_concurrency,
        ))
        deep[a.candidate.title] = (s, criteria, retrieval, screening)

    winner = tied[0]
    if len(tied) > 1:
        # Re-score on what retrieval actually found; model judgement only if still tied.
        def found(title: str) -> int:
            c = deep[title][3].counts
            return c.get(LIKELY_ELIGIBLE, 0) + c.get(UNCLEAR, 0)

        selection.rescored = rank([
            rescore(s, screened_eligible=found(s.assessment.candidate.title),
                    recent_share=shares[s.assessment.candidate.title], **score_kw)
            for s in tied
        ])
        still = tied_leaders(selection.rescored, margin=th.score_margin, max_tied=th.max_tied)
        winner = still[0]
        if len(still) > 1:
            say("Still tied after deep retrieval: tie break (5b)")
            summaries = [
                (s, f"{len(deep[s.assessment.candidate.title][2].papers)} papers retrieved; "
                    f"screened {deep[s.assessment.candidate.title][3].counts}")
                for s in still
            ]
            selection.tie_break = timed("tie_break", lambda: break_tie(
                llms["tie_break"], summaries, preferences=prefs))
            winner = still[selection.tie_break.final_choice]
    selection.winner = winner
    report.selection = selection

    top = winner.assessment
    _, criteria, retrieval, screening = deep[top.candidate.title]
    report.title = top.candidate.title
    # Named after the question actually chosen, which scoring may have changed.
    workspace = report.workspace = create_workspace(report.title, base=settings.output_dir)
    report.retrieval, report.screening = retrieval, screening
    say(f"Chosen question ({top.candidate.axis}): {report.title}")
    filled = timed("retrieval", lambda: fill_missing_dois(
        getattr(sources, "crossref", None), screening))
    if filled:
        say(f"Crossref supplied {filled} missing DOI(s)")
    search_date = today.strftime("%Y-%m-%d")
    say("Writing the guide (search strategies, protocol, PROSPERO entry)...")
    content = timed("guide", lambda: assemble(
        title=report.title, publication_type=report.publication_type, criteria=criteria,
        assessment=top, retrieval=retrieval, screening=screening, preferences=prefs,
        proforma=request.proforma, search_date=search_date, pubmed=sources.pubmed,
        llms=llms, screened_all=len(screening.papers) >= len(retrieval.papers)))
    report.content = content
    report.swap = forced is not None
    if picked_alternatives is not None:
        report.alternatives = picked_alternatives
        if len(report.alternatives) < 2:
            content.warnings.append(
                f"Only {len(report.alternatives)} alternative question(s) are left after the "
                "pick: the shortlist page offers fewer than two.")
    elif not report.swap:
        failed = {c.title for c in report.final_checks if not c.passed}
        picked = alt_mod.pick(initial, winner_title=top.candidate.title, exclude=failed)
        say(f"Writing up {len(picked)} alternative question(s)...")
        report.alternatives = timed("guide", lambda: alt_mod.build(
            picked, criteria_llm=llms["criteria_writing"],
            publication_type=report.publication_type, review_years=th.review_years))
        if len(report.alternatives) < 2:
            content.warnings.append(
                f"Only {len(report.alternatives)} alternative question(s) passed the gates: "
                "the shortlist page offers fewer than two.")
    model = build_model(content, proforma=request.proforma, retrieval_query=retrieval.query,
                        retrieval_count=retrieval.identified,
                        alternatives=[a.as_dict() for a in report.alternatives])
    say("Rendering the PDF guide, tracker, protocol and PROSPERO draft...")
    outputs = timed("guide", lambda: build_outputs(workspace, model, screenshots=screenshots,
                                                   say=say))
    report.guide_path = str(outputs["pdf"])
    report.pack_path = str(outputs["pack"])
    _finish(report, meter, settings, extra={
        "search_date": search_date,
        "title": report.title,
        "axis": top.candidate.axis,
        "rationale": top.candidate.rationale,
        "gates": [g.__dict__ for g in top.verdict.gates],
        "prospero_check": top.prospero.as_dict(),
        "searches_run": [s.__dict__ for s in top.searches],
        "selection": selection.as_dict(),
        "discovery": discovery.as_dict() if discovery else None,
        "final_checks": [c.as_dict() for c in report.final_checks],
        "novelty_checks": [c.as_dict() for c in report.novelty_checks],
        "alternatives": [a.as_dict() for a in report.alternatives],
        "swap": report.swap,
        "proforma": request.proforma,
        "guide": {
            "rationale": content.rationale,
            "warnings_for_reviewer": content.warnings,
            "strategies": [{"name": st.name, "pubmed_query": st.pubmed_query,
                            "count": st.count, "unverified_mesh": st.unverified_mesh}
                           for st in content.strategies["strategies"]],
            "recommended_strategy": content.strategies["recommended"],
            "embase_emtree": content.strategies["embase_emtree"],
            "cochrane_central": content.strategies["cochrane_central"],
            "prospero_entry": content.prospero,
            "similar_work": content.similar,
            "rob_tool": content.rob_tool,
            "timeline": [m.__dict__ for m in content.timeline],
        },
        **retrieval.as_dict(),
        **screening.as_dict(),
    })
    return report


def fill_missing_dois(crossref: Any, screening: ScreeningResult, *, limit: int = 40) -> int:
    """Look up DOIs (Crossref, title-matched) for plausibly eligible papers lacking one.

    These are the papers the user may need to fetch through their own access,
    which the guide lists by DOI.
    """
    if crossref is None:
        return 0
    filled = 0
    targets = [s for s in screening.papers
               if s.status in (LIKELY_ELIGIBLE, UNCLEAR) and not s.paper.doi][:limit]
    for s in targets:
        try:
            doi = crossref.find_doi(s.paper.title, s.paper.first_published_year)
        except httpx.HTTPError:
            continue
        if doi:
            s.paper = replace(s.paper, doi=doi)
            s.attributes["doi_source"] = "Crossref (title match)"
            filled += 1
    return filled


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
