"""`python -m guide_pipeline` — Step 0 doctor and the Step 1 live `counts` smoke check."""

from __future__ import annotations

import sys

from datetime import datetime, timezone

from .candidates import TOPIC_ANY, TOPIC_EXACT, TOPIC_SPECIALTY, RequestPreferences, screen_candidates
from .gates import LIGHTER_TYPES, SYSTEMATIC
from .guide import build_guide
from .landscape import assess_landscape
from .llm import LLMClient, LLMError, UsageMeter, build_llm, task_config
from .prospero import (
    EndpointSource,
    ProsperoError,
    ProsperoMirror,
    StaleMirrorError,
    check_title,
    delta_refresh,
    full_harvest,
    import_export_file,
)
from .retrieval import retrieve
from .screening import STATUSES, screen_papers, write_criteria
from .settings import Settings
from .sources import build_sources
from .workspace import create_workspace


def _llm(settings: Settings, task: str, meter: UsageMeter) -> LLMClient | None:
    """The configured client for `task`, or None (with a message) if unusable."""
    try:
        return build_llm(settings, task, meter=meter)
    except LLMError as exc:
        print(f"  {exc} (see .env.example)")
        return None


def _model_label(settings: Settings, task: str) -> str:
    if settings.llm_provider != "anthropic":
        return f"{settings.llm_provider}:{settings.groq_model}"
    cfg = task_config(settings, task)
    thinking = "thinking on" if cfg.thinking else "thinking off"
    return f"{cfg.model}, effort {cfg.effort}, {thinking}"


def _print_cost(meter: UsageMeter) -> None:
    if meter.calls:
        print(f"\n  Model usage: {meter.summary()}")


def doctor() -> int:
    settings = Settings.load()
    print("Guide pipeline — setup check\n")
    print(f"  LLM provider : {settings.llm_provider}")
    if settings.llm_provider == "anthropic":
        print(f"  Model        : {settings.anthropic_model} (effort set per task)")
    print(f"  Output dir   : {settings.output_dir}")
    print("  API keys:")
    for name, value in (
        ("NCBI_API_KEY", settings.ncbi_api_key),
        ("GROQ_API_KEY", settings.groq_api_key),
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
    ):
        print(f"    [{'set    ' if value else 'MISSING'}] {name}")

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    missing = settings.missing_keys()
    if missing:
        print(
            f"\n  Not ready — set: {', '.join(missing)} "
            "(copy .env.example to .env and fill it in)."
        )
        return 1
    print("\n  Ready.")
    return 0


def counts(query: str) -> int:
    """Live smoke check: print each source's count for `query` (compare to the website)."""
    settings = Settings.load()
    sources = build_sources(settings)
    print(f'Counts for: "{query}"\n')
    for label, client in (
        ("PubMed", sources.pubmed),
        ("Europe PMC", sources.europepmc),
        ("ClinicalTrials.gov", sources.clinicaltrials),
    ):
        try:
            print(f"  {label:<20} {client.count(query):>10,}")
        except Exception as exc:  # a bad query / outage shouldn't mask the others
            print(f"  {label:<20} ERROR: {exc}")
    print("\n  Compare each to the source website's result count.")
    return 0


def landscape(topic: str) -> int:
    """Step 2 live check: map `topic` to MeSH terms and print the four landscape counts."""
    settings = Settings.load()
    sources = build_sources(settings)
    result = assess_landscape(
        sources.pubmed, topic, years=settings.landscape_years
    )
    print(f'Landscape for: "{topic}"\n')
    print("  MeSH terms:")
    if result.mesh_terms:
        for term in result.mesh_terms:
            print(f"    - {term.name} ({term.ui})")
    else:
        print("    (none matched)")
    print(f"\n  Total literature       {result.total_literature:>10,}")
    print(f"  Systematic reviews     {result.systematic_reviews:>10,}")
    print(f"  Guidelines             {result.guidelines:>10,}")
    print("\n  Publications by year:")
    for year, n in result.by_year.items():
        print(f"    {year}  {n:>8,}")
    return 0


_CANDIDATES_USAGE = (
    'Usage: python -m guide_pipeline candidates "<topic>" [--type "narrative review"] '
    "[--type-flexible] [--topic exact|specialty|any] [--specialty NAME ...] "
    "[--collaborators N]"
)


def parse_candidate_args(args: list[str]) -> tuple[str, RequestPreferences]:
    """The topic plus the request preferences a proforma would supply."""
    words: list[str] = []
    pub_type, type_flexible, topic_flex = SYSTEMATIC, False, TOPIC_EXACT
    specialties: list[str] = []
    collaborators = 2
    it = iter(args)
    for arg in it:
        if arg == "--type":
            pub_type = next(it, SYSTEMATIC).lower()
            if pub_type not in (SYSTEMATIC, *LIGHTER_TYPES):
                raise ValueError(f"unknown review type: {pub_type}")
        elif arg == "--type-flexible":
            type_flexible = True
        elif arg == "--topic":
            topic_flex = next(it, TOPIC_EXACT)
            if topic_flex not in (TOPIC_EXACT, TOPIC_SPECIALTY, TOPIC_ANY):
                raise ValueError(f"--topic must be exact, specialty or any, not {topic_flex}")
        elif arg == "--specialty":
            specialties.append(next(it, ""))
        elif arg == "--collaborators":
            collaborators = int(next(it, "2"))
        else:
            words.append(arg)
    prefs = RequestPreferences(
        publication_type=pub_type,
        type_flexible=type_flexible,
        topic_flexibility=topic_flex,
        specialties=tuple(s for s in specialties if s),
        collaborators=collaborators,
    )
    return " ".join(words), prefs


def candidates(topic: str, prefs: RequestPreferences | None = None) -> int:
    """Stages 2-4 live: generate candidates, triage + gate each, rank survivors."""
    prefs = prefs or RequestPreferences()
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    llm = _llm(settings, "candidate_generation", meter)
    if llm is None:
        return 2
    mirror = ProsperoMirror(settings.prospero_db)
    print(f'Candidates for: "{topic}"  [{_model_label(settings, "candidate_generation")}]\n')
    try:
        result = screen_candidates(
            llm,
            sources.pubmed,
            sources.clinicaltrials,
            mirror,
            topic,
            settings.thresholds,
            mirror_max_age_days=settings.prospero_max_age_days,
            preferences=prefs,
        )
    except StaleMirrorError as exc:
        print(f"  REFUSING TO RUN: {exc}")
        return 1
    except LLMError as exc:
        print(f"  LLM error: {exc}")
        _print_cost(meter)
        return 1
    finally:
        mirror.close()

    for a in result.assessments:
        c = a.counts
        soon = "?" if c.trials_reporting_soon is None else f"{c.trials_reporting_soon:,}"
        top_match = a.prospero.matches[0].score if a.prospero.matches else 0.0
        print(f"  [{a.verdict.outcome.upper():<9}] {a.candidate.title}")
        print(
            f"              batch {a.batch} · {a.candidate.axis} · to screen={c.records_to_screen:,}"
            f" · eligible={c.eligible_studies:,} · recent SRs={c.recent_reviews:,}"
            f" · PROSPERO={top_match:.2f} · trials soon={soon}"
        )
        for reason in a.verdict.reasons:
            print(f"              - {reason}")
    print(f"\n  Batches generated: {result.batches}")
    print(
        f"  Request: {prefs.publication_type}"
        f" ({'type flexible' if prefs.type_flexible else 'type strict'}),"
        f" topic {prefs.topic_flexibility}"
    )
    print(f"  Outcome: {result.outcome.upper()}")
    if result.top is not None:
        kind = (
            "a scoping or narrative review"
            if result.outcome == "found_other_type"
            else prefs.publication_type
        )
        print(f"  Top pick ({kind}): {result.top.candidate.title}")
        print(f"            ({result.top.counts.eligible_studies:,} eligible studies)")
    else:
        print(f"  Email the user before going further: {result.contact_reason}.")
    _print_cost(meter)
    return 0


def retrieve_cmd(query: str) -> int:
    """Deep retrieval live check: fetch full records for a query and dedupe."""
    settings = Settings.load()
    sources = build_sources(settings)
    print(f'Retrieving for: "{query}"\n')
    result = retrieve(sources.pubmed, query, max_records=settings.thresholds.max_records_to_screen)
    for p in result.papers:
        print(f"  [{p.year or '----'}] PMID {p.pmid} — {p.title}")
    print(f"\n  {len(result.papers)} papers retrieved (deduped).")
    return 0


def guide_cmd(title: str, query: str, *, publication_type: str = SYSTEMATIC,
              limit: int | None = None) -> int:
    """Criteria, retrieval, full-recall screening, then guide.docx + results.json."""
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    llms = {t: _llm(settings, t, meter) for t in
            ("criteria_writing", "attribute_extraction", "screening", "outcome_grouping")}
    if any(v is None for v in llms.values()):
        return 2
    print(f'Building guide: "{title}"\n  query: {query}\n')
    try:
        criteria = write_criteria(llms["criteria_writing"], title,
                                  publication_type=publication_type)
        print("  Criteria:\n    " + criteria.as_text().replace("\n", "\n    "))
        retrieval = retrieve(sources.pubmed, query,
                             max_records=settings.thresholds.max_records_to_screen)
        papers = retrieval.papers[:limit] if limit else retrieval.papers
        print(f"\n  Screening {len(papers)} of {len(retrieval.papers)} retrieved papers "
              f"({settings.llm_concurrency} at a time)...")
        screening = screen_papers(
            llms["attribute_extraction"], llms["screening"], criteria, papers,
            europepmc=sources.europepmc,
            grouping_llm=llms["outcome_grouping"],
            heterogeneity_threshold=settings.thresholds.heterogeneity_max_outcomes,
            fulltext_max_chars=settings.fulltext_max_chars,
            concurrency=settings.llm_concurrency,
        )
    except LLMError as exc:
        print(f"  LLM error: {exc}")
        _print_cost(meter)
        return 1

    search_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    workspace = create_workspace(title, base=settings.output_dir)
    workspace.write_results({
        "title": title,
        "search_date": search_date,
        "publication_type": publication_type,
        **retrieval.as_dict(),
        "screened": len(papers),
        **screening.as_dict(),
        "model_cost_usd": round(meter.cost_usd, 4),
    })
    path = build_guide(workspace, title, retrieval, screening, search_date=search_date)
    print()
    for status in STATUSES:
        print(f"  {status:<26} {screening.counts.get(status, 0):>4}")
    print(f"  full text read for {screening.full_text_screened}; "
          f"{len(screening.unclear_without_open_access())} to fetch via own access")
    h = screening.heterogeneity
    if h is not None:
        print(f"  distinct primary outcomes: {h.distinct_outcomes} "
              f"({'FLAG' if h.flagged else 'ok'}, threshold {h.threshold})")
    print(f"  Wrote {path}")
    print(f"  Wrote {workspace.results_path}")
    _print_cost(meter)
    return 0


def prospero_cmd(args: list[str]) -> int:
    """PROSPERO mirror admin (spec section 3)."""
    if not args:
        print(_PROSPERO_USAGE)
        return 2
    settings = Settings.load()
    mirror = ProsperoMirror(settings.prospero_db)
    command, rest = args[0], args[1:]

    def source() -> EndpointSource:
        # NCBI_EMAIL is a personal contact given for NCBI only; not sent here.
        return EndpointSource(min_interval=settings.prospero_min_interval)

    def progress(line: str) -> None:
        print(f"  {line}", flush=True)

    try:
        if command == "status":
            info, last = mirror.coverage(), mirror.last_refresh()
            print(f"  Mirror: {settings.prospero_db}")
            print(f"  Records: {mirror.record_count():,}")
            if last is None:
                print("  Never refreshed — run `prospero harvest`.")
                return 1
            print(f"  Last refresh: {last.refreshed_at:%Y-%m-%d %H:%M} UTC ({last.mode})")
            print(f"  Covers registrations to: {info.covered_to if info else 'unknown'}")
            try:
                mirror.ensure_fresh(max_age_days=settings.prospero_max_age_days)
                print(f"  Fresh (limit {settings.prospero_max_age_days} days).")
            except StaleMirrorError as exc:
                print(f"  STALE: {exc}")
                return 1
            return 0
        unresolved: list[str] = []
        withdrawn: list[str] = []
        if command == "harvest":
            print("Full PROSPERO harvest — one-off, spaced-out requests; this takes a while.\n")
            src = source()
            summary = full_harvest(src, mirror, progress=progress)
            unresolved, withdrawn = src.unresolved, src.withdrawn
        elif command == "refresh":
            print("PROSPERO delta refresh\n")
            src = source()
            summary = delta_refresh(src, mirror, progress=progress)
            unresolved, withdrawn = src.unresolved, src.withdrawn
        elif command == "import" and rest:
            summary = import_export_file(" ".join(rest), mirror)
        elif command == "check" and rest:
            title = " ".join(rest)
            th = settings.thresholds
            result = check_title(
                mirror,
                title,
                max_age_days=settings.prospero_max_age_days,
                reject_threshold=th.prospero_reject_similarity,
                review_threshold=th.prospero_review_similarity,
            )
            print(f'PROSPERO check: "{title}"')
            print(f"  Matched on: {result.search_terms}")
            print(
                f"  Checked {result.checked_on} against the mirror "
                f"(registrations to {result.mirror_covered_to})"
            )
            print(f"  Verdict: {result.verdict.upper()}")
            for m in result.matches:
                print(f"    {m.score:.2f}  {m.registration_id}  {m.title}")
                print(f"          {m.url}")
            return 0
        else:
            print(_PROSPERO_USAGE)
            return 2
    except StaleMirrorError as exc:
        print(f"  REFUSING TO RUN: {exc}")
        return 1
    except ProsperoError as exc:
        print(f"  PROSPERO error: {exc}")
        return 1
    finally:
        mirror.close()

    print(
        f"\n  Done: +{summary.added:,} new, {summary.updated:,} updated, "
        f"{summary.windows} export(s). Mirror now holds {ProsperoMirror(settings.prospero_db).record_count():,} "
        f"records, current to {summary.covered_to}."
    )
    if withdrawn:
        print(f"  {len(withdrawn)} withdrawn protocol(s) skipped (no public title).")
    if unresolved:
        print(
            f"  {len(unresolved)} registration(s) had no retrievable title and are NOT "
            f"in the mirror: {', '.join(unresolved)}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "counts":
        if len(argv) < 2:
            print('Usage: python -m guide_pipeline counts "<query>"')
            return 2
        return counts(" ".join(argv[1:]))
    if argv and argv[0] == "landscape":
        if len(argv) < 2:
            print('Usage: python -m guide_pipeline landscape "<topic>"')
            return 2
        return landscape(" ".join(argv[1:]))
    if argv and argv[0] == "candidates":
        try:
            topic, prefs = parse_candidate_args(argv[1:])
        except ValueError as exc:
            print(f"  {exc}\n{_CANDIDATES_USAGE}")
            return 2
        if not topic:
            print(_CANDIDATES_USAGE)
            return 2
        return candidates(topic, prefs)
    if argv and argv[0] == "retrieve":
        if len(argv) < 2:
            print('Usage: python -m guide_pipeline retrieve "<pubmed query>"')
            return 2
        return retrieve_cmd(" ".join(argv[1:]))
    if argv and argv[0] == "prospero":
        return prospero_cmd(argv[1:])
    if argv and argv[0] == "guide":
        usage = ('Usage: python -m guide_pipeline guide "<title>" -- "<pubmed query>" '
                 '[--type "scoping review"] [--limit N]')
        rest = argv[1:]
        pub_type, limit = SYSTEMATIC, None
        if "--type" in rest:
            i = rest.index("--type")
            pub_type = rest[i + 1].lower() if i + 1 < len(rest) else SYSTEMATIC
            rest = rest[:i] + rest[i + 2:]
        if "--limit" in rest:
            i = rest.index("--limit")
            limit = int(rest[i + 1]) if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        if "--" not in rest:
            print(usage)
            return 2
        sep = rest.index("--")
        title, query = " ".join(rest[:sep]), " ".join(rest[sep + 1:])
        if not title or not query:
            print(usage)
            return 2
        return guide_cmd(title, query, publication_type=pub_type, limit=limit)
    return doctor()


if __name__ == "__main__":
    raise SystemExit(main())
