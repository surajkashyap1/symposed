"""The gap mining store: everything a mined run decides, kept permanently.

Local SQLite for the testing phase (decision 2026-10-24), laid out so it can
move to the website's Postgres when the question bank is built. Tables are
added milestone by milestone (`CREATE TABLE IF NOT EXISTS`), following the
spec's "Data to store" list. JSON columns hold structured detail.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS overlap_judgements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_key  TEXT NOT NULL,
    candidate      TEXT NOT NULL,   -- JSON: title and PICO as judged
    record_source  TEXT NOT NULL,   -- published review | PROSPERO | OSF
    record_id      TEXT NOT NULL,
    record_title   TEXT NOT NULL,
    record_url     TEXT,
    evidence_basis TEXT NOT NULL,
    similarity     REAL,
    overlap        TEXT NOT NULL,   -- duplicate | substantial overlap | partial overlap | none | not judged
    confidence     TEXT,
    reasoning      TEXT NOT NULL,   -- JSON: one sentence per PICO element + summary
    model          TEXT,
    judged_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS overlap_judgements_candidate_idx
    ON overlap_judgements (candidate_key);
CREATE TABLE IF NOT EXISTS overlap_verdicts (
    candidate_key TEXT NOT NULL,
    status        TEXT NOT NULL,
    reason        TEXT NOT NULL,
    model         TEXT,
    judged_at     TEXT NOT NULL,
    PRIMARY KEY (candidate_key, judged_at)
);
-- Every option the Step 3b and Step 5b filters assessed (mining/agent.py), kept so a
-- later run, for this customer or another, can reuse the work through db_lookup.
CREATE TABLE IF NOT EXISTS triage_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    stage          INTEGER NOT NULL,  -- 1 or 2
    run_key        TEXT NOT NULL,     -- the request's run folder
    candidate_id   TEXT NOT NULL,     -- the original review's PMID
    original_title TEXT NOT NULL,
    option         TEXT NOT NULL,     -- direct_update or the angle tested
    status         TEXT NOT NULL,     -- shortlisted | selected | ranked | deferred | rejected | insufficient_data
    record         TEXT NOT NULL,     -- JSON: the record exactly as the model wrote it
    model          TEXT,
    recorded_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS triage_records_candidate_idx ON triage_records (candidate_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class MiningStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def save_overlap(self, verdict: Any) -> None:
        """One overlap verdict and every record judged for it."""
        at = verdict.judged_on or _now()
        q = verdict.question
        with self._db:
            # Saving the same verdict again (a resumed run) replaces it, never duplicates.
            self._db.execute("DELETE FROM overlap_judgements WHERE candidate_key = ? "
                             "AND judged_at = ?", (q.key, at))
            self._db.execute(
                "INSERT OR REPLACE INTO overlap_verdicts (candidate_key, status, reason, model, "
                "judged_at) VALUES (?, ?, ?, ?, ?)",
                (q.key, verdict.status, verdict.reason, verdict.model, at))
            for j in verdict.judgements:
                r = j.record
                self._db.execute(
                    "INSERT INTO overlap_judgements (candidate_key, candidate, record_source, "
                    "record_id, record_title, record_url, evidence_basis, similarity, overlap, "
                    "confidence, reasoning, model, judged_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (q.key, _json(q.as_dict()), r.source, r.id, r.title, r.url, r.basis,
                     j.similarity, j.level or "not judged", j.confidence, _json(j.reasoning),
                     verdict.model, at))

    def overlap_verdicts(self, candidate_key: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT status, reason, model, judged_at FROM overlap_verdicts "
            "WHERE candidate_key = ? ORDER BY judged_at", (candidate_key,)).fetchall()
        return [dict(zip(("status", "reason", "model", "judged_at"), r)) for r in rows]

    def judgements(self, candidate_key: str) -> list[dict]:
        cur = self._db.execute(
            "SELECT record_source, record_id, overlap, confidence, reasoning, judged_at "
            "FROM overlap_judgements WHERE candidate_key = ? ORDER BY id", (candidate_key,))
        return [{"source": s, "id": i, "overlap": o, "confidence": c,
                 "reasoning": json.loads(r), "judged_at": at} for s, i, o, c, r, at in cur]

    # -- the agentic filters -------------------------------------------------------
    def save_triage(self, stage: int, run_key: str, records: list[dict], *,
                    model: str = "", at: str = "") -> None:
        """Replace this run's records for this stage (a rerun never duplicates)."""
        at = at or _now()
        with self._db:
            self._db.execute("DELETE FROM triage_records WHERE stage = ? AND run_key = ?",
                             (stage, run_key))
            for r in records:
                self._db.execute(
                    "INSERT INTO triage_records (stage, run_key, candidate_id, original_title, "
                    "option, status, record, model, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stage, run_key, str(r.get("candidate_id", "")),
                     str(r.get("original_title", "")), str(r.get("option", "")),
                     str(r.get("status", "")), _json(r.get("record", r)), model, at))

    def lookup_triage(self, query: str, *, limit: int = 10) -> list[dict]:
        """Earlier assessments matching every word of `query` (a PMID or title words)."""
        words = [w for w in query.lower().split() if len(w) > 2 or w.isdigit()][:8]
        if not words:
            return []
        where = " AND ".join(["lower(candidate_id || ' ' || original_title || ' ' || option "
                              "|| ' ' || record) LIKE ?"] * len(words))
        rows = self._db.execute(
            f"SELECT stage, run_key, candidate_id, original_title, option, status, record, "
            f"recorded_at FROM triage_records WHERE {where} ORDER BY recorded_at DESC LIMIT ?",
            [f"%{w}%" for w in words] + [limit]).fetchall()
        keys = ("stage", "run_key", "candidate_id", "original_title", "option", "status",
                "record", "recorded_at")
        out = []
        for r in rows:
            d = dict(zip(keys, r))
            d["record"] = json.loads(d["record"])
            out.append(d)
        return out
