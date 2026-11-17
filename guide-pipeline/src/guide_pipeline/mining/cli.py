"""Commands for gap mining v2: the OSF mirror and the overlap judge.

  osf harvest | refresh | status | search "<text>"
  overlap index                 embed the PROSPERO and OSF mirrors for semantic search
  overlap eval <pairs.json>     evaluate the judge on labelled pairs (calls the model)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..llm import LLMError, UsageMeter, build_llm, task_config
from ..prospero import ProsperoMirror, StaleMirrorError
from ..settings import Settings

OSF_USAGE = """Usage: python -m guide_pipeline osf <command>
  harvest [YYYY-MM] one-off: read every public OSF registration, keep health reviews
                   (~1 hour). Give the month a stopped harvest reached to resume there.
  refresh          pull registrations created or changed since the last refresh (before each run)
  status           size, coverage, fresh or STALE
  search "<text>"  lexical search of the mirror"""

OVERLAP_USAGE = """Usage: python -m guide_pipeline overlap <command>
  index              embed the PROSPERO and OSF mirrors (local model, no API cost)
  eval <pairs.json>  judge each labelled pair; report precision and recall of
                     "duplicate, high or medium confidence" (calls the model) [--sync]"""

OVERLAP_HISTORY = Path("overlap_fixtures/history.jsonl")


def _say(line: str) -> None:
    print(f"  {line}", flush=True)


def osf_cmd(args: list[str]) -> int:
    from ..osf import ApiSource, OsfError, OsfMirror, delta_refresh, full_harvest

    if not args:
        print(OSF_USAGE)
        return 2
    settings = Settings.load()
    mirror = OsfMirror(settings.osf_db)
    command, rest = args[0], args[1:]

    def source() -> ApiSource:
        return ApiSource(token=settings.osf_token, min_interval=settings.osf_min_interval)

    try:
        if command == "status":
            info, last = mirror.coverage(), mirror.last_refresh()
            print(f"  Mirror: {settings.osf_db}")
            print(f"  Registrations: {mirror.record_count():,} "
                  f"({mirror.record_count(include_withdrawn=False):,} not withdrawn)")
            if last is None:
                print("  Never refreshed: run `osf harvest`.")
                return 1
            print(f"  Last refresh: {last.refreshed_at:%Y-%m-%d %H:%M} UTC ({last.mode})")
            print(f"  Covers registrations to: {info.covered_to if info else 'unknown'}")
            try:
                mirror.ensure_fresh(max_age_days=settings.mirror_staleness_days)
                print(f"  Fresh (limit {settings.mirror_staleness_days} days).")
            except StaleMirrorError as exc:
                print(f"  STALE: {exc}")
                return 1
            return 0
        if command in ("harvest", "refresh"):
            src = source()
            if command == "harvest":
                print("Full OSF harvest: every public registration, spaced-out requests.\n")
                start = {}
                if rest:  # resume a harvest stopped by a rate limit (seen live 2026-10-27)
                    y, m = rest[0].split("-")
                    start = {"start": date(int(y), int(m), 1)}
                s = full_harvest(src, mirror, progress=_say, **start)
            else:
                print("OSF delta refresh\n")
                s = delta_refresh(src, mirror, progress=_say)
            print(f"\n  Read {s.seen:,} registrations, kept {s.kept:,}: {s.added:,} new, "
                  f"{s.updated:,} updated, in {s.windows} window(s). Covers to {s.covered_to}.")
            if src.unparsed:
                print(f"  Could not read {len(src.unparsed)}: {', '.join(src.unparsed[:20])}")
            return 0
        if command == "search" and rest:
            for m in mirror.search(" ".join(rest), limit=10):
                print(f"  {m.id}  {m.date_registered}  {m.title[:90]}\n        {m.link}")
            return 0
        print(OSF_USAGE)
        return 2
    except OsfError as exc:
        print(f"  OSF error: {exc}")
        return 1
    finally:
        mirror.close()


def overlap_cmd(args: list[str], *, sync: bool = False) -> int:
    if not args:
        print(OVERLAP_USAGE)
        return 2
    settings = Settings.load()
    command, rest = args[0], args[1:]
    if command == "index":
        return _index(settings)
    if command == "eval" and rest:
        return _eval(settings, rest[0], sync=sync)
    print(OVERLAP_USAGE)
    return 2


def _index(settings: Settings) -> int:
    from ..osf import OsfMirror
    from .embed import LocalEmbedder, VectorIndex
    from .overlap import OSF, PROSPERO

    index = VectorIndex(settings.vectors_db,
                        LocalEmbedder(settings.embedding_model, models_dir=settings.models_dir))
    print(f"Embedding the mirrors with {settings.embedding_model} (local, no API cost)\n")
    for source, path, texts in (
            (PROSPERO, settings.prospero_db, lambda: ProsperoMirror(settings.prospero_db).titles()),
            (OSF, settings.osf_db, lambda: OsfMirror(settings.osf_db).texts())):
        if not Path(path).exists():
            print(f"  {source}: no mirror at {path}, skipped")
            continue
        added = index.sync(source, texts(), progress=_say)
        print(f"  {source}: {added:,} embedded, {index.count(source):,} indexed")
    index.close()
    return 0


def _eval(settings: Settings, path: str, *, sync: bool) -> int:
    from ..osf import OsfMirror
    from ..sources import build_sources
    from .overlap_eval import PairSet, append_history, resolve_records, run_eval

    meter = UsageMeter()
    try:
        llm = build_llm(settings, "overlap_judgement", meter=meter,
                        batch=False if sync else None, progress=_say)
    except LLMError as exc:
        print(f"  {exc} (see .env.example)")
        return 2
    cfg = task_config(settings, "overlap_judgement")
    pair_set = PairSet.load(path)
    print(f"Overlap judge evaluation: {pair_set.name} ({len(pair_set.pairs)} pairs)  "
          f"[{cfg.model}, effort {cfg.effort}]")
    if pair_set.status:
        print(f"  Pair set status: {pair_set.status}")
    prospero = ProsperoMirror(settings.prospero_db) if settings.prospero_db.exists() else None
    osf = OsfMirror(settings.osf_db) if settings.osf_db.exists() else None
    records = resolve_records(pair_set.pairs, pubmed=build_sources(settings).pubmed,
                              prospero=prospero, osf=osf)
    result = run_eval(llm, pair_set, records)
    for r in result.results:
        j = r.judgement
        got = f"{j.level}, {j.confidence}" if j and j.judged else (r.error or "not judged")
        mark = "REJECTS" if r.rejects else "keeps  "
        print(f"  {r.pair.id:>4} {r.pair.label:<9} {mark} {got:<28} {r.pair.question.title[:60]}")
        if j and j.judged and (r.rejects != (r.pair.label == "duplicate")):
            print(f"         why: {j.reasoning.get('summary', '')}")
    s = result.summary()

    def pct(x):
        return "n/a" if x is None else f"{x:.0%}"
    print("\n  'Duplicate, high or medium confidence' (rejects a candidate):")
    print(f"    precision {pct(s['precision'])}  ({s['true_duplicates_rejected']} true, "
          f"{s['false_rejections']} false rejections)")
    print(f"    recall    {pct(s['recall'])}  ({s['true_duplicates_rejected']} of "
          f"{s['true_duplicates_rejected'] + s['true_duplicates_missed']} duplicates rejected)")
    for label, levels in s["table"].items():
        print(f"    {label:<9} {levels}")
    if meter.calls:
        print(f"\n  Model usage: {meter.summary()}")
    OVERLAP_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    append_history(OVERLAP_HISTORY, result, model=cfg.model)
    print(f"  (appended to {OVERLAP_HISTORY})")
    return 0


# -- the update pipeline ---------------------------------------------------------------
UPDATE_TASKS = ("topic_terms", "update_check", "review_extraction", "strategy_translation",
                "search_revision", "quick_screening",
                # step 8, the guide (unchanged)
                "search_strategy", "protocol_drafting", "prospero_form", "plain_language")

UPDATES_USAGE = """Usage: python -m guide_pipeline updates <command> <order> ...
  papers <order> <PMID>   step 6: the possibly eligible new studies for one update
  pick <order> <PMID>     step 6: pick the update to write a guide for, then run again"""


def updates_folder(settings: Settings, key: str) -> Path:
    from ..workspace import slugify

    return Path(settings.output_dir) / "updates" / slugify(key, max_len=60)


def run_updates_cmd(request, key: str, *, settings: Settings, sources, meter: UsageMeter,
                    make_llm, screenshots: bool = True) -> int:
    """`run` with CANDIDATE_SOURCE=updates: steps 1 to 8, pausing at 4 and 6."""
    from ..discovery import AwaitingFullTexts
    from ..llm_cache import cached
    from ..osf import OsfMirror
    from .agent import AgentError, StageRunner
    from .count import OverBudget
    from .embed import LocalEmbedder, VectorIndex
    from .pipeline import (AwaitingPick, BadSelection, NothingShortlisted, NoTopic,
                           run_updates)
    from .store import MiningStore

    # Direct calls only, never the Batch API: its queue can take hours (seen live
    # 2026-10-25), and these steps are waited on (Samarth).
    llms = {t: make_llm(t) for t in UPDATE_TASKS}
    if any(v is None for v in llms.values()):
        return 2
    folder = updates_folder(settings, key)
    llms = cached(llms, folder / "llm_cache")
    prospero = osf = index = embedder = None
    if not settings.skip_registry_mirrors:
        # The local similarity model is only needed to search the registry copies.
        embedder = LocalEmbedder(settings.embedding_model, models_dir=settings.models_dir)
        prospero = ProsperoMirror(settings.prospero_db)
        osf = None if settings.skip_osf_mirror else OsfMirror(settings.osf_db)
        if settings.vectors_db.exists():
            index = VectorIndex(settings.vectors_db, embedder)
    print(f"Update pipeline: topic {request.topic!r}, files in {folder}\n")
    # Step 3b and Step 5b (Samarth, 2026-10-27): direct calls on the decision model,
    # their prompts read from AGENT_PROMPTS_DIR each run.
    store = MiningStore(settings.mining_db)
    agents = StageRunner(settings, sources.pubmed, store=store, meter=meter,
                         prospero=prospero, osf=osf, say=_say)
    try:
        run = run_updates(request, settings=settings, sources=sources, llms=llms,
                          folder=folder, embedder=embedder, prospero=prospero, osf=osf,
                          index=index, screenshots=screenshots, agents=agents, say=_say)
    except AwaitingFullTexts as exc:
        print(f"\n  PAUSED at step 4: {len(exc.missing)} review full text(s) needed.")
        for r in exc.missing:
            print(f"    {r.pmid}  {r.title[:90]}")
        print(f"  Save them in {exc.folder} (see {exc.request_path}), then run again.")
        return 3
    except AwaitingPick as exc:
        sel = exc.selected
        if sel:
            print(f"\n  PAUSED at step 6. Step 5b selected PMID {sel.get('candidate_id')}: "
                  f"{sel.get('final_title')} ({sel.get('option_type')}). See {exc.table}")
            print(f"  To accept it: python -m guide_pipeline updates pick {folder.name} "
                  f"{sel.get('candidate_id')}, then run again. Picking another PMID writes "
                  "its direct update instead.")
            print("  Step 5 counts for the direct updates:")
        else:
            print(f"\n  PAUSED at step 6: eligible new studies per update (see {exc.table})")
        for i, r in enumerate(exc.rows[:20], 1):
            print(f"    {i:>2}. PMID {r['pmid']}: {r['possibly_eligible']:>3} possibly eligible "
                  f"({r['likely_eligible']} likely, {r['unclear']} unclear)  {r['title'][:70]}")
        print(f"  Look at one: python -m guide_pipeline updates papers {folder.name} <PMID>")
        print(f"  Pick one:    python -m guide_pipeline updates pick {folder.name} <PMID>, "
              "then run again.")
        return 3
    except OverBudget as exc:
        print(f"\n  PAUSED at step 5: {exc}. Raise RUN_BUDGET_USD to go ahead.")
        return 3
    except StaleMirrorError as exc:
        print(f"  REFUSING TO RUN: {exc}")
        return 1
    except (NoTopic, NothingShortlisted, BadSelection) as exc:
        print(f"  {exc}")
        return 2
    except AgentError as exc:
        print(f"  Agent stage stopped: {exc}")
        return 1
    except LLMError as exc:
        print(f"  LLM error: {exc}")
        return 1
    finally:
        store.close()
        for m in (prospero, osf, index):
            if m is not None:
                m.close()
        if meter.calls:
            print(f"\n  Model usage: {meter.summary()}")
    g = run.guide or {}
    print(f"\n  Guide: {g.get('title')}")
    for name, path in (g.get("outputs") or {}).items():
        print(f"    {name:<9} {path}")
    for w in g.get("warnings", [])[:10]:
        print(f"  ! {w}")
    return 0


def updates_cmd(args: list[str]) -> int:
    from .pipeline import load_rows, papers_text, save_pick

    if len(args) != 3 or args[0] not in ("papers", "pick"):
        print(UPDATES_USAGE)
        return 2
    command, key, pmid = args
    folder = updates_folder(Settings.load(), key)
    try:
        if command == "papers":
            row = next((r for r in load_rows(folder) if r["pmid"] == pmid), None)
            if row is None:
                print(f"  PMID {pmid} is not one of the updates in {folder / 'UPDATES.md'}")
                return 2
            print(papers_text(row))
            return 0
        row = save_pick(folder, pmid)
    except (FileNotFoundError, KeyError) as exc:
        print(f"  {exc}")
        return 2
    print(f"  Picked the update of PMID {pmid}: {row['title']}")
    print("  Run the same request again: step 7 (recall test) and step 8 (the guide) follow.")
    return 0
