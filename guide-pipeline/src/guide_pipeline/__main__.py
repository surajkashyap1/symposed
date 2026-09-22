"""`python -m guide_pipeline` — Step 0 doctor and the Step 1 live `counts` smoke check."""

from __future__ import annotations

import sys

from datetime import datetime, timezone

from .candidates import screen_candidates
from .guide import build_guide
from .landscape import assess_landscape
from .llm import LLMError, build_llm
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
    """Step 3 live check: generate candidate titles, count + gate each, rank survivors."""
    settings = Settings.load()
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        print("Set GROQ_API_KEY in .env first (LLM_PROVIDER=groq).")
        return 2
    sources = build_sources(settings)
    llm = build_llm(settings)
    print(f'Candidates for: "{topic}"  [{settings.llm_provider}:{settings.groq_model}]\n')
    try:
        result = screen_candidates(
            llm, sources.pubmed, sources.clinicaltrials, topic, settings.thresholds
        )
    except (LLMError, NotImplementedError) as exc:
        print(f"  LLM error: {exc}")
        return 1

    for a in result.assessments:
        tag = "PASS  " if a.gate.passed else "REJECT"
        trials = "?" if a.active_trials is None else f"{a.active_trials:,}"
        print(f"  [{tag}] {a.candidate.title}")
        print(
            f"          axis={a.candidate.axis or '-'} · eligible={a.eligible_studies:,}"
            f" · recent SRs={a.recent_reviews:,} · active trials={trials}"
        )
        if a.gate.reasons:
            print(f"          rejected: {'; '.join(a.gate.reasons)}")
    print()
    if result.top is not None:
        print(f"  Top pick: {result.top.candidate.title}")
        print(f"            ({result.top.eligible_studies:,} eligible studies)")
        for note in result.top.manual_checks:
            print(f"            manual: {note}")
    else:
        print("  No candidate passed the gates — try a broader or different topic.")
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
