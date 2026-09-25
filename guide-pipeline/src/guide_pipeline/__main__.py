"""`python -m guide_pipeline` — Step 0 doctor and the Step 1 live `counts` smoke check."""

from __future__ import annotations

import sys

from datetime import datetime, timezone

from .candidates import screen_candidates
from .guide import build_guide
from .landscape import assess_landscape
from .llm import LLMError, build_llm
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
from .settings import Settings
from .sources import build_sources
from .workspace import create_workspace


def doctor() -> int:
    settings = Settings.load()
    print("Guide pipeline — setup check\n")
    print(f"  LLM provider : {settings.llm_provider}")
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


def candidates(topic: str) -> int:
    """Stages 2-4 live: generate candidates, triage + gate each, rank survivors."""
    settings = Settings.load()
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        print("Set GROQ_API_KEY in .env first (LLM_PROVIDER=groq).")
        return 2
    sources = build_sources(settings)
    llm = build_llm(settings)
    mirror = ProsperoMirror(settings.prospero_db)
    print(f'Candidates for: "{topic}"  [{settings.llm_provider}:{settings.groq_model}]\n')
    try:
        result = screen_candidates(
            llm,
            sources.pubmed,
            sources.clinicaltrials,
            mirror,
            topic,
            settings.thresholds,
            mirror_max_age_days=settings.prospero_max_age_days,
        )
    except StaleMirrorError as exc:
        print(f"  REFUSING TO RUN: {exc}")
        return 1
    except (LLMError, NotImplementedError) as exc:
        print(f"  LLM error: {exc}")
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
    if result.top is not None:
        print(f"  Top pick: {result.top.candidate.title}")
        print(f"            ({result.top.counts.eligible_studies:,} eligible studies)")
    else:
        print(
            f"  No candidate passed the gates in {result.batches} batch(es) — "
            "try a broader or different topic."
        )
    if result.downgraded:
        print(f"  {len(result.downgraded)} candidate(s) could suit a scoping or narrative review.")
    return 0


def retrieve_cmd(query: str) -> int:
    """Step 4 live check: fetch full records for a chosen query, dedupe, tag."""
    settings = Settings.load()
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        print("Set GROQ_API_KEY in .env first (LLM_PROVIDER=groq).")
        return 2
    sources = build_sources(settings)
    llm = build_llm(settings)
    print(f'Retrieving for: "{query}"\n')
    try:
        result = retrieve(
            sources.pubmed,
            llm,
            query,
            max_records=settings.thresholds.max_records_to_screen,
        )
    except (LLMError, NotImplementedError) as exc:
        print(f"  LLM error: {exc}")
        return 1

    for t in result.papers:
        p = t.paper
        year = p.year or "----"
        print(f"  [{year}] PMID {p.pmid} — {p.title}")
        print(f"          use: {t.suggested_use}" + (f" — {t.reason}" if t.reason else ""))
    print(f"\n  {len(result.papers)} papers retrieved and tagged (deduped).")
    return 0


def guide_cmd(title: str, query: str) -> int:
    """Step 5: retrieve for `query`, then write the guide.docx + results.json."""
    settings = Settings.load()
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        print("Set GROQ_API_KEY in .env first (LLM_PROVIDER=groq).")
        return 2
    sources = build_sources(settings)
    llm = build_llm(settings)
    print(f'Building guide: "{title}"\n  query: {query}\n')
    try:
        result = retrieve(
            sources.pubmed,
            llm,
            query,
            max_records=settings.thresholds.max_records_to_screen,
        )
    except (LLMError, NotImplementedError) as exc:
        print(f"  LLM error: {exc}")
        return 1

    search_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    workspace = create_workspace(title, base=settings.output_dir)
    workspace.write_results(
        {"title": title, "search_date": search_date, **result.as_dict()}
    )
    path = build_guide(workspace, title, result, search_date=search_date)
    print(f"  {len(result.papers)} papers retrieved.")
    print(f"  Wrote {path}")
    print(f"  Wrote {workspace.results_path}")
    return 0


_PROSPERO_USAGE = """Usage: python -m guide_pipeline prospero <command>
  status              mirror size, coverage and freshness
  harvest             one-off full download of the register (slow; run once)
  refresh             pull registrations since the last refresh (weekly)
  import <file>       merge an export downloaded by hand (RIS or CSV)
  check "<title>"     fuzzy-check a title against the mirror"""


def prospero_cmd(args: list[str]) -> int:
    """PROSPERO mirror admin (spec section 3)."""
    if not args:
        print(_PROSPERO_USAGE)
        return 2
    settings = Settings.load()
    mirror = ProsperoMirror(settings.prospero_db)
    command, rest = args[0], args[1:]

    def source() -> EndpointSource:
        agent = "symposed-guide-pipeline"
        if settings.ncbi_email:
            agent += f" ({settings.ncbi_email})"
        return EndpointSource(min_interval=settings.prospero_min_interval, user_agent=agent)

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
        if len(argv) < 2:
            print('Usage: python -m guide_pipeline candidates "<topic>"')
            return 2
        return candidates(" ".join(argv[1:]))
    if argv and argv[0] == "retrieve":
        if len(argv) < 2:
            print('Usage: python -m guide_pipeline retrieve "<pubmed query>"')
            return 2
        return retrieve_cmd(" ".join(argv[1:]))
    if argv and argv[0] == "prospero":
        return prospero_cmd(argv[1:])
    if argv and argv[0] == "guide":
        rest = argv[1:]
        if not rest:
            print('Usage: python -m guide_pipeline guide "<title>" -- "<pubmed query>"')
            return 2
        if "--" in rest:
            sep = rest.index("--")
            title = " ".join(rest[:sep])
            query = " ".join(rest[sep + 1 :])
        else:  # no separator: use the text as both title and query
            title = query = " ".join(rest)
        if not query:
            print('Usage: python -m guide_pipeline guide "<title>" -- "<pubmed query>"')
            return 2
        return guide_cmd(title, query)
    return doctor()


if __name__ == "__main__":
    raise SystemExit(main())
