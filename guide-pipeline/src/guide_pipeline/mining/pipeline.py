"""The update pipeline, steps 1 to 8 (docs/spec-update-pipeline.md).

  1. Registry copies up to date (PROSPERO and OSF), unless skipped for testing.
  2. Topic terms from the proforma, each searched on its own.
  3. At least 50 systematic reviews, published more than 3 years ago and not
     already updated (no later review repeats the work, no update registered).
  4. Full texts of the passing reviews, supplied by hand. Search date, search
     strategy, criteria and included studies are read out of them.
  5. Each review's own search run for records since its search ended, every hit
     screened: the number of eligible new studies per update, in UPDATES.md.
  6. PAUSE: Samarth looks at the eligible studies (`updates papers`) and picks
     one update (`updates pick`).
  7. The recall test of the search the guide will use.
  8. The guide.

Every pause is resumed by running the same command again. API responses and
model replies are cached, so nothing already done is paid for twice, and the
prompts are deterministic so the cache keeps matching.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..candidates import SearchRun
from ..discovery import SKIP_SUFFIX, AwaitingFullTexts, FullTextStore, ReviewRef
from ..llm import LLMError
from ..plain import tidy
from ..screening import Criteria, screen_quick
from ..sources.pubmed import Paper
from .count import (COST_PER_PAPER_USD, OverBudget, UpdateCount, UpdateSearch, _check,
                    find_new, screen_new, translate_all)
from .extract import Extraction, extract_all
from .overlap import CLEAR
from .guide import ANGLE_AXIS, UPDATE_AXIS, build_guide
from .recall_check import RecallResult, run_recall_test
from .reviews import (AlreadyCheck, Found, check_already_updated, citation,
                      extract_topic_terms, find_reviews, looks_like_prose,
                      sample_all_reviews, sample_reviews, topic_terms)
from .store import MiningStore

UPDATES_JSON = "updates.json"
SEARCHES_JSON = "searches.json"
PICK_JSON = "pick.json"
SKIPPED_MIRRORS = ("PROSPERO and OSF were not checked for registered updates "
                   "(SKIP_REGISTRY_MIRRORS=true, for testing).")
SKIPPED_OSF = ("OSF was not checked for registered updates (SKIP_OSF_MIRROR=true, for "
               "testing). PROSPERO was checked.")

Say = Callable[[str], None]


class NoTopic(Exception):
    """The proforma gave no topic to search."""


class NothingShortlisted(Exception):
    """Step 3b shortlisted no usable option."""


class BadSelection(Exception):
    """Step 5b's selected option cannot be run as given (its search fails or is too broad)."""


class AwaitingPick(Exception):
    """Step 6: a person picks the update to write a guide for."""

    def __init__(self, folder: Path, table: Path, rows: list[dict],
                 selected: Optional[dict] = None):
        self.folder, self.table, self.rows = folder, table, rows
        self.selected = selected or {}  # Step 5b's choice, when it ran
        super().__init__(f"pick an update: see {table}")


class UpdateFullTexts(FullTextStore):
    """Supplied full texts only: no automatic download (step 4)."""

    def write_request(self, stage: str, refs: list[ReviewRef], missing: list[ReviewRef]) -> Path:
        path = self.folder / "NEEDED.md"
        lines = [
            f"# Full texts needed ({stage})", "",
            "These reviews passed step 3: old enough and not already updated. Save each one "
            f"in `{self.folder}` named by its PMID, as `.pdf`, `.docx`, `.txt` or `.md`. "
            "The pipeline reads its search date, search strategy, inclusion criteria and "
            "included studies from it.",
            f"If you cannot get one, create an empty `<PMID>{SKIP_SUFFIX}` file and that review "
            "is left out. Then run the same command again.", "",
            "| Save as | Review | Journal, year | Links |", "|---|---|---|---|",
        ]
        for r in missing:
            bad = self.unreadable(r.pmid)
            note = (f" (no text could be read from {', '.join(f'`{p.name}`' for p in bad)}: "
                    "paste the text into Word instead)") if bad else ""
            doi = f" · [DOI](https://doi.org/{r.doi})" if r.doi else ""
            lines.append(f"| `{r.pmid}.pdf`{note} | {r.title} | {r.journal}, {r.year or ''} | "
                         f"[PubMed]({r.url}){doi} |")
        have = [r for r in refs if r not in missing]
        if have:
            lines += ["", "Already supplied:", ""] + [f"- {r.pmid}: {r.title}" for r in have]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


@dataclass
class UpdateRun:
    folder: Path
    terms: list[str]
    found: Optional[Found] = None
    checks: list[AlreadyCheck] = field(default_factory=list)
    skipped: list[Paper] = field(default_factory=list)       # step 4: no full text
    extractions: dict[str, Extraction] = field(default_factory=dict)
    counts: list[UpdateCount] = field(default_factory=list)
    pick: Optional[str] = None
    recall: Optional[RecallResult] = None
    guide: Optional[dict] = None
    warnings: list[str] = field(default_factory=list)
    sample_note: str = ""
    named: list[Paper] = field(default_factory=list)  # REVIEW_PMIDS, in place of step 3
    stage1: Optional[dict] = None   # the triage agent's shortlist (mining/agent.py)
    stage2: Optional[dict] = None   # the appraisal agent's selection


def _today():
    return datetime.now(timezone.utc).date()


def run_updates(request: Any, *, settings: Any, sources: Any, llms: dict[str, Any],
                folder: Path, embedder: Any = None, prospero: Any = None, osf: Any = None,
                index: Any = None, screenshots: bool = True, agents: Any = None,
                say: Say = lambda _m: None) -> UpdateRun:
    """Steps 1 to 8. `agents` runs Step 3b and Step 5b (agent.StageRunner): without
    it every review that passes step 3 goes on to step 4, as before the stages."""
    cfg = settings.updates
    pubmed = sources.pubmed
    folder.mkdir(parents=True, exist_ok=True)
    run = UpdateRun(folder, topic_terms(request.topic,
                                        str(request.proforma.get("existingTitle") or "")))

    # Step 1
    if settings.skip_registry_mirrors:
        run.warnings.append(SKIPPED_MIRRORS)
        prospero = osf = None
        say("Step 1: registry checks skipped (testing).")
    else:
        prospero.ensure_fresh(max_age_days=settings.prospero_max_age_days)
        if getattr(settings, "skip_osf_mirror", False):
            osf = None
            run.warnings.append(SKIPPED_OSF)
            say("Step 1: PROSPERO copy is up to date. OSF skipped (testing).")
        else:
            osf.ensure_fresh(max_age_days=settings.mirror_staleness_days)
            say("Step 1: PROSPERO and OSF copies are up to date.")

    # Step 2: no topic means the whole literature (Samarth, 2026-10-27). A topic written
    # as sentences is turned into short terms by the quick model first.
    if looks_like_prose(request.topic) and llms.get("topic_terms") is not None:
        run.terms = extract_topic_terms(llms["topic_terms"], request.topic,
                                        str(request.proforma.get("existingTitle") or ""))
        say("Step 2: the topic was written as prose, so search terms were drawn from it")
    if run.terms:
        say(f"Step 2: topic terms {', '.join(repr(t) for t in run.terms)}")
    else:
        say("Step 2: no topic given, so reviews are drawn from the whole literature")

    # Step 3, or the reviews a person names (REVIEW_PMIDS): those skip the search and
    # the novelty check, and REVIEWS.md says so.
    if cfg.review_pmids:
        passing = pubmed.fetch_details(list(cfg.review_pmids))
        run.named = passing
        write_named_table(folder / "REVIEWS_NAMED.md", run)
        say(f"Step 3: skipped, using the {len(passing)} named reviews")
    else:
        pool = cfg.review_count * cfg.review_pool_factor
        if run.terms:
            run.found = find_reviews(pubmed, run.terms, count=pool,
                                     min_age_years=cfg.review_min_age_years)
        else:
            run.found = sample_all_reviews(pubmed, count=pool,
                                           min_age_years=cfg.review_min_age_years,
                                           since_year=cfg.blank_topic_since_year,
                                           seed=folder.name)
        say(f"Step 3: {len(run.found.reviews)} systematic reviews published before "
            f"{run.found.cutoff} drawn, checked in batches until {cfg.review_count} pass")
        if cfg.review_sample or cfg.review_sample_min_age_years:
            n = len(run.found.reviews)
            run.found.reviews = sample_reviews(run.found, min_age_years=cfg.review_sample_min_age_years,
                                               size=cfg.review_sample, seed=folder.name)
            run.sample_note = (f"Narrowed from {n} found to {len(run.found.reviews)}: "
                               + (f"published more than {cfg.review_sample_min_age_years} years ago"
                                  if cfg.review_sample_min_age_years else "")
                               + (", " if cfg.review_sample_min_age_years and cfg.review_sample else "")
                               + (f"a fixed random sample of at most {cfg.review_sample}"
                                  if cfg.review_sample else "") + ".")
            say(f"  {run.sample_note}")
        say("  checking each for a later update...")
        run.checks = []
        reviews = run.found.reviews
        store = MiningStore(settings.mining_db)
        for start in range(0, len(reviews), cfg.review_batch):
            run.checks += check_already_updated(
                reviews[start:start + cfg.review_batch], llm=llms["update_check"],
                pubmed=pubmed, europepmc=getattr(sources, "europepmc", None),
                prospero=prospero, osf=osf, embedder=embedder, index=index,
                k=cfg.overlap_retrieval_k, judged_on=_today().isoformat(), store=store,
                say=say)
            failed = [c for c in run.checks if c.verdict.error]
            if failed:
                # A judge that could not run (seen live 2026-10-27: no API credit) must stop
                # the run, never let the review through unjudged. Judged ones are cached.
                store.close()
                raise LLMError(f"The novelty judge failed for {len(failed)} review(s), e.g. "
                               f"PMID {failed[0].review.pmid}: {failed[0].verdict.error}")
            for c in run.checks[-cfg.review_batch:]:
                store.save_overlap(c.verdict)  # saved as it goes, so a stop loses nothing
            n_pass = sum(c.passes for c in run.checks)
            say(f"  {len(run.checks)} checked, {n_pass} pass")
            if n_pass >= cfg.review_count:
                break
        run.found.reviews = [c.review for c in run.checks]  # the rest were never needed
        store.close()
        passing = [c.review for c in run.checks if c.passes][:cfg.review_count]
        if len(passing) < cfg.review_count:
            run.warnings.append(f"Only {len(passing)} of the {len(run.checks)} reviews drawn "
                                f"passed step 3, fewer than the {cfg.review_count} wanted.")
        write_reviews_table(folder / "REVIEWS.md", run)
        say(f"  {len(passing)} not already updated (see {folder / 'REVIEWS.md'})")

    # Step 3b (Samarth, 2026-10-27): the triage agent shortlists five options from the
    # abstracts, so full texts are asked for only for those.
    if agents is not None and passing:
        say(f"Step 3b: the triage agent is assessing {len(passing)} reviews "
            "(this can take a while)...")
        run.stage1 = agents.stage1(request=request, folder=folder,
                                   reviews=[(p, _flagged(p, run, cfg)) for p in passing])
        ids = [str(t.get("candidate_id")) for t in run.stage1["output"].get("top_5") or []]
        passing = [p for i in dict.fromkeys(ids) for p in passing if p.pmid == i]
        if not passing:
            raise NothingShortlisted(f"Step 3b shortlisted no usable option: see "
                                     f"{folder / 'STAGE1.md'}")
        say(f"  shortlisted {len(passing)}: {', '.join(p.pmid for p in passing)} "
            f"(see {folder / 'STAGE1.md'})")

    # Step 4
    fts = UpdateFullTexts(folder / "fulltexts", None)
    refs = [ReviewRef.from_paper(p) for p in passing]
    fts.require(refs, stage="step 4: review full texts")
    items = []
    for p, ref in zip(passing, refs):
        text, basis = fts.text(ref)
        if text:
            items.append((p, text, basis))
        else:
            run.skipped.append(p)
    say(f"Step 4: reading {len(items)} full texts...")
    run.extractions = {e.pmid: e for e in extract_all(llms["review_extraction"], items)}

    # Step 5
    usable = [(p, run.extractions[p.pmid]) for p, _, _ in items
              if not run.extractions[p.pmid].error]
    say(f"Step 5: translating {len(usable)} search strategies and counting new studies...")
    searches = frozen_searches(folder / SEARCHES_JSON, llms["strategy_translation"], pubmed,
                               usable)
    found_new = find_new(pubmed, [(p, ex, s) for (p, ex), s in zip(usable, searches)],
                         max_hits=cfg.max_hits)
    run.counts = screen_new(llms["quick_screening"], pubmed, found_new,
                            run.extractions, budget_usd=cfg.run_budget_usd,
                            concurrency=settings.llm_concurrency)
    rows = write_updates(folder, run, min_new=cfg.min_new_eligible)

    # Step 5b: the appraisal agent reads the full texts and the step 5 counts, and
    # selects the one option the guide is written for.
    if agents is not None and run.stage1:
        say(f"Step 5b: the appraisal agent is reading {len(items)} full texts "
            "(this can take a while)...")
        run.stage2 = agents.stage2(request=request, stage1=run.stage1, folder=folder,
                                   documents=[(p, t) for p, t, _ in items],
                                   screening=screening_summary(rows))
    selected = ((run.stage2 or {}).get("output") or {}).get("selected") or {}

    # Step 6
    pick_path = folder / PICK_JSON
    if not pick_path.exists():
        raise AwaitingPick(folder, folder / ("STAGE2.md" if run.stage2 else "UPDATES.md"),
                           rows, selected)
    run.pick = json.loads(pick_path.read_text(encoding="utf-8"))["pmid"]
    review = next(p for p, _ in usable if p.pmid == run.pick)
    ex = run.extractions[run.pick]
    if selected and str(selected.get("candidate_id")) == run.pick:
        say(f"Step 6: picked Step 5b's selection: {selected.get('final_title', '')}")
        run.recall, run.guide = run_selected(
            selected, review=review, ex=ex, request=request, settings=settings,
            sources=sources, llms=llms, folder=folder, warnings=list(run.warnings),
            screenshots=screenshots, say=say)
        return run
    count = next(c for c in run.counts if c.pmid == run.pick)
    say(f"Step 6: picked the update of PMID {run.pick}: {review.title}")

    # Step 7
    say("Step 7: recall test of the search on the original review's included studies...")
    run.recall = run_recall_test(
        pubmed, pmid=run.pick, query=count.search.pubmed_query, criteria=ex.criteria,
        studies=ex.included_studies, revise_llm=llms["search_revision"],
        screen_llm=llms["quick_screening"],
        search_target=cfg.search_recall_min, screen_target=cfg.screen_recall_min,
        max_revisions=cfg.max_search_revisions)
    query = run.recall.final.query
    if query != count.search.pubmed_query:
        # The guide's search changed: count and screen the new records again with it.
        count.search.pubmed_query = query
        count = screen_new(llms["quick_screening"], pubmed,
                           find_new(pubmed, [(review, ex, count.search)], max_hits=cfg.max_hits),
                           run.extractions, budget_usd=cfg.run_budget_usd,
                           concurrency=settings.llm_concurrency)[0]
    write_recall(folder / "RECALL.md", run.recall, review)
    warnings = list(run.warnings) + list(ex.warnings)
    if not run.recall.passed:
        warnings.append("The recall test did not reach its targets: see RECALL.md before "
                        "trusting the recommended search.")

    # Step 8
    say("Step 8: writing the guide...")
    run.guide = build_guide(review=review, extraction=ex, count=count, query=query,
                            request=request, settings=settings, sources=sources, llms=llms,
                            warnings=warnings, screenshots=screenshots, say=say)
    return run


# -- the agentic stages ---------------------------------------------------------------
def _flagged(review: Paper, run: UpdateRun, cfg: Any) -> str:
    """Why the pipeline put this review forward, for Step 3b."""
    if any(p.pmid == review.pmid for p in run.named):
        return ("Named by Symposed staff for this request: the step 3 search and novelty "
                "check were skipped for it.")
    check = next((c for c in run.checks if c.review.pmid == review.pmid), None)
    why = (f"Published more than {cfg.review_min_age_years} years ago. The step 3 novelty "
           "check found no later review that updates it")
    if check is not None and check.verdict.reason:
        why += f" ({check.verdict.reason})"
    return why + "."


def screening_summary(rows: list[dict], *, sample: int = 30) -> list[dict]:
    """Step 5's counts for each shortlisted direct update, for Step 5b."""
    out = []
    for r in rows:
        likely = [p for p in r["papers"] if p["status"] == "likely eligible"]
        out.append({
            "candidate_id": r["pmid"], "direct_update_pubmed_query": r["update"]["pubmed_query"],
            "original_search_end": r["search_end"],
            "search_end_estimated": r["search_end_estimated"],
            "records_added_since_search_end": r["hits"], "too_broad": r["too_broad"],
            "likely_eligible": r["likely_eligible"], "unclear": r["unclear"],
            "possibly_eligible": r["possibly_eligible"],
            "method": "every record screened by title and abstract against the original "
                      "review's criteria (quick model, estimates only)",
            "likely_eligible_examples": [{"pmid": p["pmid"], "year": p["year"],
                                          "title": p["title"]} for p in likely[:sample]],
            "error": r["error"]})
    return out


def criteria_from_spec(sel: dict) -> Criteria:
    pico = sel.get("pico") or {}
    outcomes = pico.get("outcomes") or []
    return Criteria(
        population=str(pico.get("population", "")),
        intervention_or_exposure=str(pico.get("exposure_or_intervention", "")),
        comparator=str(pico.get("comparator", "")),
        outcomes=". ".join(map(str, outcomes)) if isinstance(outcomes, list) else str(outcomes),
        study_designs="As in the inclusion criteria",
        setting=str(pico.get("setting", "")),
        other_inclusion=tuple(map(str, sel.get("inclusion_criteria") or [])),
        exclusion=tuple(map(str, sel.get("exclusion_criteria") or [])))


UPDATE_TYPES = ("direct_update", "upgraded_update")


def clean_query(query: str) -> str:
    """A model's PubMed search with any trailing note removed (seen live 2026-10-27:
    '... NOT (animals[mh] NOT humans[mh]); date 2017 to present'). A year range in
    the note becomes a publication date limit."""
    query = query.strip()
    if ";" not in query:
        return query
    base, note = (x.strip() for x in query.split(";", 1))
    m = re.search(r"(\d{4})\s*(?:to|-|–)\s*(present|now|\d{4})", note, re.I)
    if m:
        end = m.group(2) if m.group(2).isdigit() else "3000"
        base = f'({base}) AND ("{m.group(1)}"[dp] : "{end}"[dp])'
    return base


def run_selected(sel: dict, *, review: Paper, ex: Extraction, request: Any, settings: Any,
                 sources: Any, llms: dict[str, Any], folder: Path, warnings: list[str],
                 screenshots: bool, say: Say) -> tuple[Optional[RecallResult], dict]:
    """Steps 5, 7 and 8 for the option Step 5b selected, using its own search and
    criteria. An update counts records added since the original search ended, an
    alternative angle counts every record."""
    cfg, pubmed = settings.updates, sources.pubmed
    query = clean_query(str((sel.get("search_strings") or {}).get("pubmed", "")))
    problem = _check(pubmed, query)
    if problem:
        raise BadSelection(f"Step 5b's PubMed search cannot be run: {problem}. Edit "
                           f"selected.search_strings.pubmed in {folder / 'stage2.json'} and run "
                           "again.")
    criteria = criteria_from_spec(sel)
    is_update = sel.get("option_type") in UPDATE_TYPES
    since = ex.search_end + timedelta(days=1) if is_update and ex.search_end else None

    def count(q: str) -> UpdateCount:
        today = _today()
        n, ids = pubmed.search_dated(q, datetype="edat",
                                     mindate=since.strftime("%Y/%m/%d") if since else None,
                                     maxdate=today.strftime("%Y/%m/%d"), retmax=cfg.max_hits)
        if n > cfg.max_hits:
            raise BadSelection(f"Step 5b's search finds {n:,} records, more than MAX_HITS "
                               f"({cfg.max_hits:,}). Narrow it in {folder / 'stage2.json'}.")
        if n * COST_PER_PAPER_USD > cfg.run_budget_usd:
            raise OverBudget(n, n * COST_PER_PAPER_USD, cfg.run_budget_usd)
        say(f"Step 5: screening the {n:,} records Step 5b's search finds...")
        (screened,) = screen_quick(llms["quick_screening"],
                                   [(criteria, pubmed.fetch_details(ids))],
                                   concurrency=settings.llm_concurrency)
        window = f"added {since} to {today}" if since else f"all records to {today}"
        notes = [str((sel.get("search_strings") or {}).get("adaptation_notes", ""))]
        return UpdateCount(review.pmid, UpdateSearch(q, [x for x in notes if x], False), since,
                           hits=n, screening=screened,
                           searches=[SearchRun("PubMed", f"{q} ({window})", n,
                                               datetime.now(timezone.utc).isoformat())])

    uc = count(query)
    recall = None
    if is_update:
        say("Step 7: recall test of the search on the original review's included studies...")
        recall = run_recall_test(
            pubmed, pmid=review.pmid, query=query, criteria=criteria,
            studies=ex.included_studies, revise_llm=llms["search_revision"],
            screen_llm=llms["quick_screening"], search_target=cfg.search_recall_min,
            screen_target=cfg.screen_recall_min, max_revisions=cfg.max_search_revisions)
        if recall.final.query != query:
            query = recall.final.query
            uc = count(query)
        write_recall(folder / "RECALL.md", recall, review)
        if not recall.passed:
            warnings.append("The recall test did not reach its targets: see RECALL.md before "
                            "trusting the recommended search.")
    else:
        warnings.append("This is an alternative angle, so the recall test on the original "
                        "review's included studies was not run: they fall outside the new "
                        "question. Check the search by hand.")
    est = sel.get("estimated_eligible") or {}
    differs = tidy(str(sel.get("differs_from_original", "")))
    rationale = (f"{sel.get('research_question', '')} {differs} Step 5b estimated "
                 f"{est.get('low', '?')} to {est.get('high', '?')} eligible studies "
                 f"({est.get('method', 'method not stated')}). The pipeline's screen found "
                 f"{len(uc.possibly_eligible)} possibly eligible records.")
    say("Step 8: writing the guide...")
    guide = build_guide(
        review=review, extraction=replace(ex, criteria=criteria), count=uc, query=query,
        request=request, settings=settings, sources=sources, llms=llms,
        warnings=warnings + list(ex.warnings), screenshots=screenshots, say=say,
        title=str(sel.get("final_title") or ""),
        axis=UPDATE_AXIS if is_update else ANGLE_AXIS, rationale=rationale,
        kind=str(sel.get("option_type") or "selected").replace("_", "-"),
        parallel=tidy(f"This review builds on {citation(review)} {differs}"),
        parallel_difference=differs, extra_results={"stage2_selected": sel})
    return recall, guide


# -- what a person reads -------------------------------------------------------------
def write_reviews_table(path: Path, run: UpdateRun) -> None:
    f = run.found
    lines = [f"# Step 3: systematic reviews considered ({len(run.checks)})", "",
             f"Topic terms: {', '.join(run.terms) or 'none (the whole literature)'}. "
             f"Published before {f.cutoff}. "
             "Each was checked for a later paper that repeats its work, by two PubMed "
             "searches on its title words (one with PubMed's systematic review filter, one "
             "with no filter, plus PubMed's similar articles), and for a registered update "
             "on PROSPERO and OSF.",
             ""] + ([run.sample_note, ""] if run.sample_note else [])
    lines += [f"> {w}" for w in run.warnings] + ([""] if run.warnings else [])
    lines += ["| PMID | Review | Year | Already updated? | Why |", "|---|---|---|---|---|"]
    for c in run.checks:
        r, v = c.review, c.verdict
        mark = "no, passes" if c.passes else "YES, left out"
        if c.passes and v.status != CLEAR:
            mark = f"no, but {v.status.split(', ', 1)[-1]}"
        lines.append(f"| [{r.pmid}](https://pubmed.ncbi.nlm.nih.gov/{r.pmid}/) | {r.title} | "
                     f"{r.first_published_year or r.year or ''} | {mark} | "
                     f"{v.reason.replace('|', '/')} |")
    lines += ["", "Searches run:", ""] + [f"- {s.query}: {s.result:,} records ({s.run_at})"
                                          for s in f.searches]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def frozen_searches(path: Path, llm: Any, pubmed: Any,
                    usable: list[tuple[Paper, Extraction]]) -> list[UpdateSearch]:
    """Each review's translated search, made once and then reused from `path`.

    A regenerated translation can differ (seen live 2026-10-25: 246 then 471 records
    for the same review), so counts would drift between runs. Delete a review's
    entry in searches.json to have it translated again.
    """
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    todo = [(p, ex) for p, ex in usable if p.pmid not in saved]
    for (p, _), s in zip(todo, translate_all(llm, pubmed, todo) if todo else []):
        if s.pubmed_query and not s.error:
            saved[p.pmid] = asdict(s)
    path.write_text(json.dumps(saved, indent=1, ensure_ascii=False), encoding="utf-8")
    fresh = {p.pmid: UpdateSearch(**saved[p.pmid]) for p, _ in usable if p.pmid in saved}
    out = []
    for p, ex in usable:
        out.append(fresh.get(p.pmid) or UpdateSearch("", [], False, error="translation failed"))
    return out


def write_named_table(path: Path, run: UpdateRun) -> None:
    lines = ["# Step 3: skipped", "",
             "These reviews were named by a person (REVIEW_PMIDS), so the search for "
             "reviews and the check for later updates were not run for them.", ""]
    lines += [f"> {w}" for w in run.warnings] + ([""] if run.warnings else [])
    lines += [f"- [{p.pmid}](https://pubmed.ncbi.nlm.nih.gov/{p.pmid}/) "
              f"({p.first_published_year or p.year or ''}) {p.title}" for p in run.named]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_updates(folder: Path, run: UpdateRun, *, min_new: int) -> list[dict]:
    """UPDATES.md (the step 5 table) and updates.json (what step 6 reads)."""
    by_pmid = {c.review.pmid: c.review for c in run.checks}
    by_pmid.update({p.pmid: p for p in run.named})
    rows = []
    for c in run.counts:
        r, ex = by_pmid[c.pmid], run.extractions[c.pmid]
        rows.append({"pmid": c.pmid, "title": r.title, "citation": citation(r),
                     "search_end": ex.search_end.isoformat() if ex.search_end else None,
                     "search_end_estimated": ex.search_end_estimated,
                     "original_included": ex.included_count, **c.counts(),
                     "hits": c.hits, "too_broad": c.too_broad,
                     "built_from_criteria": c.search.built_from_criteria,
                     "error": c.search.error, "warnings": ex.warnings,
                     "papers": [{"pmid": s.paper.pmid, "title": s.paper.title,
                                 "year": s.paper.first_published_year or s.paper.year,
                                 "status": s.status, "reason": s.reason}
                                for s in (c.screening.papers if c.screening else [])],
                     "update": c.as_dict()})
    rows.sort(key=lambda x: -x["possibly_eligible"])
    (folder / UPDATES_JSON).write_text(json.dumps({
        "rows": rows, "skipped": [{"pmid": p.pmid, "title": p.title} for p in run.skipped],
        "warnings": run.warnings}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = ["# Step 5: eligible new studies for each update", "",
             "Each review's own search, run for records added to PubMed after its search "
             "ended, with every new record screened by title and abstract against the "
             "review's own criteria. Possibly eligible = likely eligible + unclear.", ""]
    lines += [f"> {w}" for w in run.warnings] + ([""] if run.warnings else [])
    lines += ["| # | PMID | Review | Search ended | Original studies | New records | "
              "Likely eligible | Unclear | Possibly eligible | Notes |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(rows, 1):
        notes = []
        if x["search_end_estimated"]:
            notes.append("search date estimated")
        if x["built_from_criteria"]:
            notes.append("search built from criteria")
        if x["too_broad"]:
            notes.append(f"over {x['hits']:,} records: too broad, not screened")
        if x["error"]:
            notes.append(f"search failed: {x['error']}")
        if x["possibly_eligible"] < min_new:
            notes.append(f"fewer than {min_new}")
        lines.append(f"| {i} | {x['pmid']} | {x['title']} | {x['search_end'] or 'unknown'} | "
                     f"{x['original_included'] if x['original_included'] is not None else '?'} | "
                     f"{x['hits']:,} | {x['likely_eligible']} | {x['unclear']} | "
                     f"**{x['possibly_eligible']}** | {'; '.join(notes)} |")
    if run.skipped:
        lines += ["", "Left out (no full text supplied):", ""]
        lines += [f"- {p.pmid}: {p.title}" for p in run.skipped]
    lines += ["", "Next: look at an update's studies with "
              f"`python -m guide_pipeline updates papers {folder.name} <PMID>`, then pick one "
              f"with `python -m guide_pipeline updates pick {folder.name} <PMID>` and run again."]
    (folder / "UPDATES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def write_recall(path: Path, r: RecallResult, review: Paper) -> None:
    def pct(x):
        return "n/a" if x is None else f"{x:.0%}"
    lines = [f"# Step 7: recall test, update of PMID {review.pmid}", "", review.title, "",
             f"Result: **{'PASSED' if r.passed else 'BELOW TARGET'}**. Search recall "
             f"{pct(r.final.search_recall)} (target {pct(r.search_target)}), screening recall "
             f"{pct(r.screen_recall)} (target {pct(r.screen_target)}).", "",
             f"Included studies matched to PubMed: {len(r.matched)}. Not matched (left out): "
             f"{len(r.unmatched)}.", ""]
    for i, a in enumerate(r.attempts):
        lines += [f"## {'Original translation' if i == 0 else f'Revision {i}'}", "",
                  f"Found {len(a.found)} of {len(a.found) + len(a.missed)} "
                  f"({pct(a.search_recall)}).", "", "```", a.query, "```", ""]
        if a.missed:
            lines.append("Missed: " + ", ".join(a.missed))
        for d in a.diagnoses:
            lines.append(f"- PMID {d.get('pmid')}: {d.get('reason')}")
        if a.changes:
            lines += ["", "Changes in the next revision:"] + [f"- {c}" for c in a.changes]
        lines.append("")
    if r.screened_dropped:
        lines += ["## Found by the search but screened out", ""]
        lines += [f"- PMID {d['pmid']}: {d['title']} ({d['reason']})" for d in r.screened_dropped]
    if r.unmatched:
        lines += ["", "## Included studies not matched to PubMed", ""]
        lines += [f"- {s.get('first_author')} {s.get('year')}: {s.get('title') or '(no title)'}"
                  for s in r.unmatched]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- step 6 commands -------------------------------------------------------------------
def load_rows(folder: Path) -> list[dict]:
    path = folder / UPDATES_JSON
    if not path.exists():
        raise FileNotFoundError(f"No step 5 results in {folder}: run the request first.")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def papers_text(row: dict) -> str:
    """The possibly eligible studies for one update, PMIDs first."""
    keep = [p for p in row["papers"] if p["status"] != "likely ineligible"]
    lines = [f"Update of PMID {row['pmid']}: {row['title']}",
             f"{len(keep)} possibly eligible of {len(row['papers'])} new records "
             f"(search ended {row['search_end'] or 'unknown'}).", "",
             "PMIDs: " + ", ".join(p["pmid"] for p in keep), ""]
    for p in keep:
        lines.append(f"{p['pmid']}  {p['year'] or ''}  [{p['status']}]  {p['title']}")
        lines.append(f"    {p['reason']}")
    return "\n".join(lines)


def save_pick(folder: Path, pmid: str) -> dict:
    rows = load_rows(folder)
    row = next((r for r in rows if r["pmid"] == pmid), None)
    if row is None:
        raise KeyError(f"PMID {pmid} is not one of the updates in {folder / 'UPDATES.md'}")
    (folder / PICK_JSON).write_text(json.dumps({"pmid": pmid, "picked_at": datetime.now(
        timezone.utc).isoformat(timespec="seconds")}), encoding="utf-8")
    return row


__all__ = ["AwaitingFullTexts", "AwaitingPick", "BadSelection", "NoTopic",
           "NothingShortlisted", "OverBudget", "UpdateRun",
           "run_updates", "load_rows", "papers_text", "save_pick"]
