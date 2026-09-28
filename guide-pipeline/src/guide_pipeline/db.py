"""The pipeline's side of the website database (build spec §5, A7).

The pipeline reads paid guide orders and writes each run — candidates with
their gate results, every search, the screened papers with their graded status,
the PROSPERO check record, any tie break and the draft guide — in one
transaction per run. The admin verification screen (Stage 6) reads these rows
and records the reviewer's decision.

Which orders get a run: paid orders with no run yet, or whose latest run
failed or was rejected by the reviewer. A run awaiting review is left alone.
Titles already offered to another customer, and titles rejected for this one,
are passed to generation as "avoid" so no question is offered twice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from .prospero import match_key


def host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or "(unknown host)"
    except ValueError:
        return "(unparseable)"


def connect(url: str):
    import psycopg

    return psycopg.connect(url, prepare_threshold=None, autocommit=False)


def _json(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(json.loads(json.dumps(value, default=str)))


@dataclass(frozen=True)
class Order:
    id: str
    proforma: dict


ORDERS_TO_PROCESS = """
select o.id, o.proforma
from guide_orders o
left join lateral (
  select r.id, r.status from guide_runs r
  where r.order_id = o.id order by r.started_at desc limit 1
) last_run on true
left join lateral (
  select v.action from guide_verifications v
  where v.run_id = last_run.id order by v.created_at desc limit 1
) last_verdict on true
where o.status in ('paid', 'in_progress')
  and (last_run.id is null
       or last_run.status = 'failed'
       or last_verdict.action = 'rejected')
order by o.paid_at nulls last, o.created_at
"""


def orders_to_process(conn) -> list[Order]:
    with conn.cursor() as cur:
        cur.execute(ORDERS_TO_PROCESS)
        return [Order(str(r[0]), json.loads(r[1])) for r in cur.fetchall()]


def titles_to_avoid(conn, order_id: str) -> list[str]:
    """Titles offered to other customers, plus titles rejected for this order."""
    with conn.cursor() as cur:
        cur.execute(
            "select title from guide_title_registry "
            "where order_id is distinct from %s or status = 'rejected'",
            (order_id,),
        )
        return [r[0] for r in cur.fetchall()]


def start_run(conn, order_id: Optional[str], pipeline_version: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "insert into guide_runs (order_id, status, pipeline_version) "
            "values (%s, 'running', %s) returning id",
            (order_id, pipeline_version),
        )
        run_id = str(cur.fetchone()[0])
        if order_id:
            cur.execute(
                "update guide_orders set status = 'in_progress', updated_at = now() "
                "where id = %s and status = 'paid'",
                (order_id,),
            )
    conn.commit()
    return run_id


def fail_run(conn, run_id: str, error: str) -> None:
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "update guide_runs set status = 'failed', finished_at = now(), "
            "results = %s where id = %s",
            (_json({"error": error}), run_id),
        )
    conn.commit()


def save_run(conn, run_id: str, report: Any, *, docx: Optional[bytes]) -> None:
    """Write a finished run and everything it produced, in one transaction."""
    results = json.loads(report.workspace.results_path.read_text(encoding="utf-8"))
    screen = report.screen
    selection = report.selection
    scores = {s.assessment.candidate.title: s.as_dict()
              for s in (selection.initial if selection else [])}
    top = selection.winner.assessment if selection and selection.winner else None
    order_id = report.request.order_id or None
    with conn.cursor() as cur:
        cur.execute(
            "update guide_runs set status = %s, title = %s, publication_type = %s, "
            "axis = %s, contact_reason = %s, cost_usd = %s, results = %s, metrics = %s, "
            "guide_docx = %s, finished_at = now() where id = %s",
            (report.outcome if report.outcome != "found_other_type" else "found",
             report.title or None, report.publication_type or None,
             top.candidate.axis if top else None,
             getattr(screen, "contact_reason", "") or None,
             report.metrics.get("cost_usd"), _json(results), _json(report.metrics),
             docx, run_id),
        )
        for a in screen.assessments:
            cur.execute(
                "insert into guide_run_candidates (run_id, title, normalized_title, axis, "
                "batch, outcome, gates, score, eligible_studies, recent_reviews) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (run_id, a.candidate.title, match_key(a.candidate.title), a.candidate.axis,
                 a.batch, a.verdict.outcome, _json([g.__dict__ for g in a.verdict.gates]),
                 _json(scores[a.candidate.title]) if a.candidate.title in scores else None,
                 a.counts.eligible_studies, a.counts.recent_reviews),
            )
        searches = (report.content.search_appendix if report.content
                    else [{"source": s.source, "query": s.query, "count": s.result,
                           "run_at": s.run_at} for a in screen.assessments for s in a.searches])
        for s in searches:
            cur.execute(
                "insert into guide_searches (run_id, source, query, result_count, run_at) "
                "values (%s, %s, %s, %s, %s)",
                (run_id, s["source"], s["query"], s["count"], str(s["run_at"])),
            )
        if report.screening is not None:
            for sp in report.screening.papers:
                p = sp.paper
                cur.execute(
                    "insert into guide_screened_papers (run_id, identifier, id_type, doi, "
                    "title, year, journal, status, reason, evidence_basis, attributes) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (run_id, p.pmid, p.id_type, p.doi, p.title, p.year, p.journal,
                     sp.status, sp.reason, sp.evidence_basis, _json(sp.attributes)),
                )
        if top is not None and top.prospero is not None:
            pc = top.prospero.as_dict()
            cur.execute(
                "insert into guide_prospero_checks (run_id, title, search_terms, checked_on, "
                "mirror_covered_to, mirror_refreshed_at, verdict, matches) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (run_id, pc["title"], pc["search_terms"], pc["checked_on"],
                 pc["mirror_covered_to"], pc["mirror_refreshed_at"], pc["verdict"],
                 _json(pc["matches"])),
            )
        if selection is not None and selection.tie_break is not None:
            tb = selection.tie_break
            cur.execute(
                "insert into guide_tie_breaks (run_id, candidates, model_choice, rationale, "
                "summary) values (%s, %s, %s, %s, %s)",
                (run_id, _json(tb.candidates), tb.choice, _json(tb.rationale), tb.summary),
            )
        if report.title:
            # One question, one customer: the primary key refuses a second offer.
            cur.execute(
                "insert into guide_title_registry (normalized_title, title, first_run_id, "
                "order_id) values (%s, %s, %s, %s) on conflict (normalized_title) do nothing",
                (match_key(report.title), report.title, run_id, order_id),
            )
    conn.commit()
