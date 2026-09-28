import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from guide_pipeline import db
from guide_pipeline.candidates import Candidate, CandidateAssessment, SearchRun
from guide_pipeline.gates import GateResult, GateVerdict, TriageCounts
from guide_pipeline.prospero import ProsperoCheck
from guide_pipeline.screening import UNCLEAR, Criteria, ScreenedPaper, ScreeningResult
from guide_pipeline.sources.pubmed import Paper


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.conn.rows

    def fetchone(self):
        return ("run-1",)


class FakeConn:
    def __init__(self, rows=()):
        self.statements, self.rows, self.commits, self.rollbacks = [], list(rows), 0, 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def sql(self, prefix):
        return [s for s in self.statements if s[0].lower().startswith(prefix)]


def test_orders_and_avoid_list():
    conn = FakeConn(rows=[("o1", json.dumps({"topics": "x"}))])
    (order,) = db.orders_to_process(conn)
    assert (order.id, order.proforma) == ("o1", {"topics": "x"})
    sql = conn.statements[0][0]
    assert "last_verdict.action = 'rejected'" in sql and "last_run.status = 'failed'" in sql
    conn = FakeConn(rows=[("Taken elsewhere",)])
    assert db.titles_to_avoid(conn, "o1") == ["Taken elsewhere"]
    assert conn.statements[0][1] == ("o1",)


def test_start_run_marks_order_in_progress():
    conn = FakeConn()
    assert db.start_run(conn, "o1", "abc123") == "run-1"
    assert conn.sql("update guide_orders set status = 'in_progress'")
    assert conn.commits == 1


def test_failed_run_rolls_back_then_records_the_error():
    conn = FakeConn()
    db.fail_run(conn, "run-1", "LLMError: boom")
    assert conn.rollbacks == 1 and conn.commits == 1
    assert "status = 'failed'" in conn.statements[0][0]


def _report(tmp_path):
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"title": "Winner", "metrics": {}}))
    a = CandidateAssessment(
        candidate=Candidate("Winner", "Discordance", "q"),
        counts=TriageCounts(100, 30, 0, 0),
        verdict=GateVerdict("pass", [GateResult("too_few_studies", "pass", 30, 8, "")]),
        prospero=ProsperoCheck("Winner", "winner", date(2026, 9, 28), date(2026, 9, 28),
                               datetime(2026, 9, 28, tzinfo=timezone.utc), "clear", []),
        searches=[SearchRun("PubMed", "q", 100, "2026-09-28T10:00:00")],
    )
    score = SimpleNamespace(assessment=a, as_dict=lambda: {"total": 0.9})
    paper = Paper("PPR1", "A preprint", "abs", (), "medRxiv (preprint)", 2025, None,
                  id_type="PPR", source="Europe PMC (preprint)")
    return SimpleNamespace(
        request=SimpleNamespace(order_id="o1"), outcome="found", title="Winner",
        publication_type="systematic review", metrics={"cost_usd": 1.23},
        workspace=SimpleNamespace(results_path=results),
        screen=SimpleNamespace(assessments=[a], contact_reason=""),
        selection=SimpleNamespace(initial=[score], winner=score, tie_break=None),
        screening=ScreeningResult(Criteria("p", "i", "c", "o", "d"),
                                  [ScreenedPaper(paper, {}, UNCLEAR, "r", "abstract only")]),
        content=None,
    )


def test_save_run_writes_every_record_in_one_transaction(tmp_path):
    conn = FakeConn()
    db.save_run(conn, "run-1", _report(tmp_path), docx=b"DOCX")
    update = conn.sql("update guide_runs")[0][1]
    assert update[0] == "found" and update[1] == "Winner" and update[-2] == b"DOCX"
    assert len(conn.sql("insert into guide_run_candidates")) == 1
    assert len(conn.sql("insert into guide_searches")) == 1
    paper = conn.sql("insert into guide_screened_papers")[0][1]
    assert paper[1:3] == ("PPR1", "PPR")  # preprint id kept as such
    assert conn.sql("insert into guide_prospero_checks")
    registry = conn.sql("insert into guide_title_registry")[0]
    assert "on conflict (normalized_title) do nothing" in registry[0]
    assert registry[1][0] == "winner" and registry[1][3] == "o1"
    assert conn.commits == 1  # a single transaction


def test_host_is_shown_without_credentials():
    assert db.host_of("postgresql://u:secret@db.example.co:5432/postgres") == "db.example.co"
