"""`python -m guide_pipeline` — Step 0 doctor and the Step 1 live `counts` smoke check."""

from __future__ import annotations

import sys

from datetime import datetime, timezone
from pathlib import Path as _Path

from .candidates import TOPIC_ANY, TOPIC_EXACT, TOPIC_SPECIALTY, RequestPreferences, screen_candidates
from .gates import LIGHTER_TYPES, SYSTEMATIC
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
from .request import from_proforma
from .run import run_request, summarise_metrics
from .recall import Fixture, append_history, run_consistency, run_recall
from .screening import STATUSES
from .settings import Settings
from .sources import build_sources
from .workspace import create_workspace


# Set by --sync: per-paper steps run as parallel calls (fast, full price)
# instead of through the Batch API (half price, minutes to hours).
_SYNC = False


def _llm(settings: Settings, task: str, meter: UsageMeter) -> LLMClient | None:
    """The configured client for `task`, or None (with a message) if unusable."""
    try:
        return build_llm(settings, task, meter=meter, batch=False if _SYNC else None,
                         progress=lambda m: print(f"    {m}", flush=True))
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


HISTORY = "recall_fixtures/history.jsonl"


def _discovery_setup(settings, sources, llms, key: str, *, abstracts_ok: bool = False):
    """The per-request folder that survives pauses: supplied full texts and the
    cached model replies that make a resumed run free up to where it stopped."""
    from .discovery import FullTextStore
    from .llm_cache import cached
    from .workspace import slugify

    folder = _Path(settings.output_dir) / "discovery" / slugify(key, max_len=60)
    store = FullTextStore(folder / "fulltexts", getattr(sources, "europepmc", None),
                          openalex=getattr(sources, "openalex", None),
                          abstracts_ok=abstracts_ok)
    return folder, store, cached(llms, folder / "llm_cache")


def _print_pause(exc) -> None:
    from .shortlist import AwaitingChoice

    if isinstance(exc, AwaitingChoice):
        print(f"\n  PAUSED: pick a question.{(' ' + exc.note) if exc.note else ''}")
        for o in exc.options:
            print(f"    {o.number}. {o.title}")
        print(f"  Read {exc.path} (or send {exc.folder / 'shortlist.docx'}),")
        print(f"  then: python -m guide_pipeline pick {exc.folder.name} <number>, and run again.")
        return
    print(f"\n  PAUSED: {len(exc.missing)} full text(s) needed for {exc.stage}.")
    for r in exc.missing:
        print(f"    {r.pmid}  {r.title[:90]}")
    print(f"  Save them in {exc.folder} (see {exc.request_path}),")
    print("  then run the same command again. Nothing already done is paid for twice.")
RUN_TASKS = ("candidate_generation", "criteria_writing", "attribute_extraction",
             "screening", "outcome_grouping", "tie_break", "search_strategy",
             "protocol_drafting", "prospero_form", "plain_language",
             # review led discovery
             "topic_generation", "review_reading", "gap_candidates", "axis_lens",
             "final_check", "shortlist_brief", "novelty_check")


def run_cmd(path: str, limit: int | None = None, abstracts_ok: bool = False) -> int:
    """One request end to end: a proforma JSON file in, a draft guide + metrics out.

    The file holds the website's proforma answers, either bare or as
    {"order_id": ..., "proforma": {...}}.
    """
    import json as _json
    from pathlib import Path as _Path

    data = _json.loads(_Path(path).read_text(encoding="utf-8"))
    proforma = data.get("proforma", data)
    request = from_proforma(proforma, order_id=str(data.get("order_id", "")))
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    llms = {t: _llm(settings, t, meter) for t in RUN_TASKS}
    if any(v is None for v in llms.values()):
        return 2
    prefs = request.preferences
    print(f"Guide request {request.order_id or path}")
    print(f"  {prefs.publication_type} "
          f"({'type flexible' if prefs.type_flexible else 'type strict'}), "
          f"topic {'BLANK' if request.blank_topic else repr(request.topic)} "
          f"(flexibility: {prefs.topic_flexibility}), team of {prefs.collaborators}")
    batch = settings.llm_batch and not _SYNC and settings.llm_provider == "anthropic"
    print(f"  per-paper steps: {'Batch API (half price)' if batch else 'parallel calls'}\n")
    from .discovery import AwaitingFullTexts
    from .shortlist import AwaitingChoice

    store = choose_dir = None
    if settings.discovery_mode == "reviews":
        folder, store, llms = _discovery_setup(
            settings, sources, llms, request.order_id or _Path(path).stem,
            abstracts_ok=abstracts_ok)
        choose_dir = folder if settings.pick_before_guide else None
        print(f"  review led discovery, files in {folder}\n")
    mirror = ProsperoMirror(settings.prospero_db)
    try:
        report = run_request(request, settings=settings, sources=sources, mirror=mirror,
                             llms=llms, meter=meter, limit=limit, store=store,
                             choose_dir=choose_dir,
                             progress=lambda m: print(f"  {m}", flush=True))
    except (AwaitingFullTexts, AwaitingChoice) as exc:
        _print_pause(exc)
        _print_cost(meter)
        return 3
    except StaleMirrorError as exc:
        print(f"  REFUSING TO RUN: {exc}")
        return 1
    except LLMError as exc:
        print(f"  LLM error: {exc}")
        _print_cost(meter)
        return 1
    finally:
        mirror.close()
    m = report.metrics
    print(f"\n  Outcome: {report.outcome.upper()}")
    print(f"  Candidates: {m['candidates_generated']} in {m['batches']} batch(es), "
          f"{m['candidates_passed']} passed")
    if report.screening is not None:
        for status, n in report.screening.counts.items():
            print(f"  {status:<26} {n:>4}")
        print(f"  Guide: {report.guide_path}")
        print(f"  Files: {report.pack_path}")
    print(f"  Results: {report.workspace.results_path}")
    print(f"  Time: {m['seconds_total']:.0f}s  "
          f"Cost: ${m['cost_usd']:.2f} (candidates ${m['cost_candidates_usd']:.2f}, "
          f"screening ${m['cost_screening_usd']:.2f})")
    print(f"  Metrics appended to {settings.output_dir}/metrics.jsonl")
    return 0


def swap_cmd(run_folder: str, number: int, *, limit: int | None = None,
             save: bool = False) -> int:
    """A customer chose alternative `number` from a delivered guide.

    Re-runs the novelty checks (gates and PROSPERO) on that title today, since
    the shortlist date is weeks old, and if it still passes writes its full
    guide. With --save the run is recorded for the order like a batch run, for
    review and delivery in /admin/guides.
    """
    import json as _json

    from .candidates import Candidate

    results = _json.loads((_Path(run_folder) / "results.json").read_text(encoding="utf-8"))
    alts = {a["number"]: a for a in results.get("alternatives") or []}
    if number not in alts:
        print(f"  No alternative {number} in {run_folder} (has: {sorted(alts) or 'none'})")
        return 2
    if "proforma" not in results:
        print("  This run predates swaps (no proforma saved in results.json).")
        return 2
    a = alts[number]
    forced = Candidate(a["title"], a.get("axis") or "Swap", a["search_query"],
                       a.get("trials_query", ""), a.get("rationale", ""))
    request = from_proforma(results["proforma"], order_id=str(results.get("order_id") or ""))
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    llms = {t: _llm(settings, t, meter) for t in RUN_TASKS}
    if any(v is None for v in llms.values()):
        return 2
    print(f"Swap for order {request.order_id or '(none)'}: alternative {number}\n  {a['title']}")
    print(f"  shortlist checked {a.get('prospero_checked_on')}; re-checking today\n")
    conn = run_id = None
    if save:
        from . import db
        from .run import _git_version

        if not settings.database_url:
            print("  --save needs PIPELINE_DATABASE_URL (or STAGING_DATABASE_URL).")
            return 2
        conn = db.connect(settings.database_url)
        run_id = db.start_run(conn, request.order_id or None, _git_version())
    mirror = ProsperoMirror(settings.prospero_db)
    try:
        report = run_request(request, settings=settings, sources=sources, mirror=mirror,
                             llms=llms, meter=meter, limit=limit, forced=forced,
                             progress=lambda m: print(f"  {m}", flush=True))
        if conn is not None:
            from . import db

            pack = _Path(report.pack_path).read_bytes() if report.pack_path else None
            db.save_run(conn, run_id, report, docx=pack)
    except Exception as exc:
        if conn is not None:
            from . import db

            db.fail_run(conn, run_id, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        mirror.close()
        if conn is not None:
            conn.close()
    print(f"\n  Outcome: {report.outcome.upper()}")
    if report.outcome != "found":
        print(f"  {report.screen.contact_reason}")
        print("  Tell the customer before charging: the question needs refining first.")
    else:
        print(f"  Guide: {report.guide_path}\n  Files: {report.pack_path}")
    _print_cost(meter)
    return 0 if report.outcome == "found" else 1


def pick_cmd(key: str, number: int) -> int:
    """Record which shortlisted question to write the guide for."""
    from .shortlist import SHORTLIST_MD, failed_checks, write_choice
    from .workspace import slugify

    settings = Settings.load()
    folder = _Path(settings.output_dir) / "discovery" / slugify(key, max_len=60)
    shortlist = folder / SHORTLIST_MD
    if not shortlist.exists():
        print(f"No shortlist for {key} (looked for {shortlist}).")
        return 1
    text = shortlist.read_text(encoding="utf-8")
    heading = next((line for line in text.splitlines()
                    if line.lstrip("#").strip().startswith(f"Option {number}: ")), None)
    if heading is None:
        print(f"There is no option {number} in {shortlist}.")
        return 1
    title = heading.split(": ", 1)[1]
    if title in failed_checks(folder):
        print(f"Option {number} already failed the final check. Pick another.")
        return 1
    write_choice(folder, number)
    print(f"Picked option {number}: {title}\nRun the batch (or the run command) again "
          "to check it once more and write its guide.")
    return 0


def batch_cmd(limit: int | None = None, max_orders: int | None = None) -> int:
    """The Friday batch: refresh PROSPERO, then run every order that needs a run."""
    from . import db
    from .run import _git_version

    settings = Settings.load()
    if not settings.database_url:
        print("Set PIPELINE_DATABASE_URL (or STAGING_DATABASE_URL) in .env first.")
        return 2
    print(f"Guide batch against database host: {db.host_of(settings.database_url)}\n")
    if prospero_cmd(["refresh"]) != 0:
        print("  PROSPERO refresh failed: not processing any orders on a stale mirror.")
        return 1
    sources = build_sources(settings)
    conn = db.connect(settings.database_url)
    try:
        orders = db.orders_to_process(conn)[:max_orders] if max_orders else db.orders_to_process(conn)
        print(f"\n{len(orders)} order(s) to process")
        failures = 0
        paused: list = []
        for order in orders:
            meter = UsageMeter()
            llms = {t: _llm(settings, t, meter) for t in RUN_TASKS}
            if any(v is None for v in llms.values()):
                return 2
            request = from_proforma(order.proforma, order_id=order.id)
            avoid = db.titles_to_avoid(conn, order.id)
            run_id = db.start_run(conn, order.id, _git_version())
            print(f"\n== Order {order.id} (run {run_id}); avoiding {len(avoid)} title(s)")
            from .discovery import AwaitingFullTexts
            from .shortlist import AwaitingChoice

            store = choose_dir = None
            if settings.discovery_mode == "reviews":
                folder, store, llms = _discovery_setup(settings, sources, llms, order.id)
                choose_dir = folder if settings.pick_before_guide else None
            mirror = ProsperoMirror(settings.prospero_db)
            try:
                try:
                    report = run_request(request, settings=settings, sources=sources,
                                         mirror=mirror, llms=llms, meter=meter, limit=limit,
                                         avoid_titles=tuple(avoid), store=store,
                                         choose_dir=choose_dir,
                                         progress=lambda m: print(f"  {m}", flush=True))
                except (AwaitingFullTexts, AwaitingChoice) as exc:
                    # No run row for a paused order: the next batch picks it up
                    # again and the cached replay resumes it.
                    db.discard_run(conn, run_id)
                    paused.append((order.id, exc))
                    _print_pause(exc)
                    continue
                pack = None
                if report.pack_path:
                    from pathlib import Path as _Path
                    pack = _Path(report.pack_path).read_bytes()
                # The guide_docx column now holds the zip of the PDF guide and its
                # companion files; the admin download serves it as a .zip.
                db.save_run(conn, run_id, report, docx=pack)
                print(f"  -> {report.outcome}: {report.title or report.screen.contact_reason}"
                      f"  (${report.metrics.get('cost_usd', 0):.2f})")
            except Exception as exc:  # one order failing must not stop the batch
                failures += 1
                db.fail_run(conn, run_id, f"{type(exc).__name__}: {exc}")
                print(f"  -> FAILED: {type(exc).__name__}: {exc}")
            finally:
                mirror.close()
        print(f"\nBatch done: {len(orders) - failures - len(paused)} run(s) saved, "
              f"{failures} failed, {len(paused)} waiting for full texts or a pick. "
              "Review them in /admin/guides.")
        for order_id, exc in paused:
            if isinstance(exc, AwaitingChoice):
                print(f"  waiting: order {order_id}: pick a question, see {exc.path}")
            else:
                print(f"  waiting: order {order_id}: {len(exc.missing)} file(s), "
                      f"see {exc.request_path}")
        return 0 if not failures else 1
    finally:
        conn.close()


def metrics_cmd() -> int:
    """Averages across all recorded runs, blank topic vs topic given."""
    import json as _json
    from pathlib import Path as _Path

    settings = Settings.load()
    path = _Path(settings.output_dir) / "metrics.jsonl"
    if not path.exists():
        print("No runs recorded yet.")
        return 1
    print(_json.dumps(summarise_metrics(path), indent=2))
    return 0


def _screen_llms(settings: Settings, meter: UsageMeter):
    extract = _llm(settings, "attribute_extraction", meter)
    screen = _llm(settings, "screening", meter)
    return extract, screen


def recall_cmd(path: str, others: int = 0) -> int:
    """Recall test on a known review (spec update acceptance test)."""
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    extract, screen = _screen_llms(settings, meter)
    if extract is None or screen is None:
        return 2
    fixture = Fixture.load(path)
    print(f"Recall test: {fixture.name}  [{_model_label(settings, 'screening')}]\n")
    r = run_recall(fixture, sources.pubmed, extract, screen, europepmc=sources.europepmc,
                   others=others, concurrency=settings.llm_concurrency,
                   fulltext_max_chars=settings.fulltext_max_chars)
    for status, n in r.counts(r.included).items():
        print(f"  included studies {status:<26} {n:>3}")
    print(f"\n  RECALL: {len(r.flagged)}/{len(r.included)} = {r.recall:.1%}"
          " (likely eligible or unclear)")
    if r.not_retrieved:
        print(f"  not returned by PubMed: {', '.join(r.not_retrieved)}")
    for s in r.missed:
        print(f"  MISSED PMID {s.paper.pmid} ({s.evidence_basis}): {s.paper.title[:80]}")
        print(f"         reason: {s.reason}")
    if r.others:
        print(f"\n  other papers from the search: {r.counts(r.others)}")
    _print_cost(meter)
    append_history(HISTORY, {
        "test": "recall", "fixture": fixture.name, "recall": round(r.recall, 4),
        "included_screened": len(r.included), "missed_pmids": [s.paper.pmid for s in r.missed],
        "counts": r.counts(r.included), "screening": _model_label(settings, "screening"),
        "cost_usd": round(meter.cost_usd, 4),
    })
    print(f"  (appended to {HISTORY})")
    return 0


def consistency_cmd(path: str, papers: int = 5) -> int:
    """Screen the same papers twice; report any status that changes."""
    settings = Settings.load()
    sources = build_sources(settings)
    meter = UsageMeter()
    extract, screen = _screen_llms(settings, meter)
    if extract is None or screen is None:
        return 2
    fixture = Fixture.load(path)
    print(f"Consistency test: {fixture.name}, {papers} papers x 2 runs\n")
    c = run_consistency(fixture, sources.pubmed, extract, screen, papers=papers,
                        europepmc=sources.europepmc, concurrency=settings.llm_concurrency)
    for a, b in c.pairs:
        mark = "FLIP " if (a, b) in c.flipped else ("change" if a.status != b.status else "same ")
        print(f"  [{mark}] PMID {a.paper.pmid}: {a.status} | {b.status}")
    print(f"\n  {len(c.pairs) - len(c.changed)}/{len(c.pairs)} identical status; "
          f"{len(c.flipped)} eligible/ineligible flip(s)")
    _print_cost(meter)
    append_history(HISTORY, {
        "test": "consistency", "fixture": fixture.name, "papers": len(c.pairs),
        "changed": len(c.changed), "flipped": len(c.flipped),
        "screening": _model_label(settings, "screening"), "cost_usd": round(meter.cost_usd, 4),
    })
    return 0 if not c.flipped else 1


def main(argv: list[str] | None = None) -> int:
    global _SYNC
    argv = sys.argv[1:] if argv is None else argv
    if "--sync" in argv:
        _SYNC = True
        argv = [a for a in argv if a != "--sync"]
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
    if argv and argv[0] == "run":
        rest = argv[1:]
        limit = None
        if "--limit" in rest:
            i = rest.index("--limit")
            limit = int(rest[i + 1])
            rest = rest[:i] + rest[i + 2:]
        abstracts_ok = "--abstracts-ok" in rest
        rest = [a for a in rest if a != "--abstracts-ok"]
        if not rest:
            print("Usage: python -m guide_pipeline run <request.json> [--limit N] [--sync] "
                  "[--abstracts-ok]\n  Review led discovery pauses when it needs full texts; "
                  "run again to resume.\n  --abstracts-ok: use abstracts for any review "
                  "still missing instead of pausing.")
            return 2
        return run_cmd(rest[0], limit=limit, abstracts_ok=abstracts_ok)
    if argv and argv[0] == "pick":
        if len(argv) != 3 or not argv[2].isdigit():
            print("Usage: python -m guide_pipeline pick <order id> <number>\n"
                  "  Picks a question from the order's SHORTLIST.md. Run the batch again "
                  "to write its guide.")
            return 2
        return pick_cmd(argv[1], int(argv[2]))
    if argv and argv[0] == "swap":
        rest = argv[1:]
        limit = None
        if "--limit" in rest:
            i = rest.index("--limit")
            limit = int(rest[i + 1])
            rest = rest[:i] + rest[i + 2:]
        save = "--save" in rest
        rest = [x for x in rest if x != "--save"]
        if len(rest) != 2 or not rest[1].isdigit():
            print("Usage: python -m guide_pipeline swap <run folder> <1|2> [--save] [--limit N]\n"
                  "  Re-checks the chosen alternative today, then writes its full guide.\n"
                  "  --save records the run for the order (review it in /admin/guides).")
            return 2
        return swap_cmd(rest[0], int(rest[1]), limit=limit, save=save)
    if argv and argv[0] == "batch":
        rest = argv[1:]
        opts = {}
        for flag in ("--limit", "--max-orders"):
            if flag in rest:
                i = rest.index(flag)
                opts[flag] = int(rest[i + 1])
                rest = rest[:i] + rest[i + 2:]
        return batch_cmd(limit=opts.get("--limit"), max_orders=opts.get("--max-orders"))
    if argv and argv[0] == "metrics":
        return metrics_cmd()
    if argv and argv[0] in ("recall", "consistency"):
        rest = argv[1:]
        n = None
        for flag in ("--others", "--papers"):
            if flag in rest:
                i = rest.index(flag)
                n = int(rest[i + 1])
                rest = rest[:i] + rest[i + 2:]
        if not rest:
            print(f"Usage: python -m guide_pipeline {argv[0]} <fixture.json> "
                  f"[{'--others N' if argv[0] == 'recall' else '--papers N'}]")
            return 2
        if argv[0] == "recall":
            return recall_cmd(rest[0], others=n or 0)
        return consistency_cmd(rest[0], papers=n or 5)
    if argv and argv[0] == "prospero":
        return prospero_cmd(argv[1:])
    if argv and argv[0] == "render":
        rest = [a for a in argv[1:] if a != "--shots"]
        if not rest:
            print("Usage: python -m guide_pipeline render <run folder> [--shots]\n"
                  "Rebuilds guide.pdf and the companion files from guide_model.json "
                  "(no model calls). --shots retakes the PubMed screenshots.")
            return 2
        from .deliver import rerender
        out = rerender(rest[0], screenshots="--shots" in argv)
        for name, path in out.items():
            print(f"  {name:<9} {path}")
        return 0
    if argv and argv[0] == "guide":
        print("The guide command was replaced by: python -m guide_pipeline run <request.json>")
        return 2
    return doctor()


if __name__ == "__main__":
    raise SystemExit(main())
