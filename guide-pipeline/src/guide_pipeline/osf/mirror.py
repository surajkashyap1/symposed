"""The local OSF mirror: storage, merge, refresh log, staleness guard, search.

SQLite with an FTS5 index on each registration's normalised title and
description, the same pattern as the PROSPERO mirror. Search here is lexical
only; the overlap judge adds semantic similarity on top (mining/overlap.py).
Withdrawn registrations are kept, marked, and never returned by search: they
block nothing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from ..prospero.mirror import RefreshInfo, StaleMirrorError
from ..prospero.records import match_key
from .records import OsfRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS osf_mirror (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    registration_schema TEXT,
    date_registered     TEXT,
    date_modified       TEXT,
    subjects            TEXT,
    tags                TEXT,
    withdrawn           INTEGER NOT NULL DEFAULT 0,
    link                TEXT NOT NULL,
    normalised          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS osf_fts USING fts5(id UNINDEXED, normalised);
CREATE TABLE IF NOT EXISTS osf_refreshes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    refreshed_at    TEXT NOT NULL,
    mode            TEXT NOT NULL,
    covered_to      TEXT,
    seen            INTEGER NOT NULL,
    records_added   INTEGER NOT NULL,
    records_updated INTEGER NOT NULL
);
"""
_SEP = "\x1f"  # joins subjects and tags in one column


@dataclass(frozen=True)
class OsfMatch:
    id: str
    title: str
    description: str
    registration_schema: str
    date_registered: Optional[date]
    link: str
    rank: float  # bm25, lower is better


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _date(text: Optional[str]) -> Optional[date]:
    return date.fromisoformat(text) if text else None


class OsfMirror:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # -- writes ------------------------------------------------------------------
    def merge(self, records: Iterable[OsfRecord]) -> tuple[int, int]:
        """Upsert records; returns (added, updated)."""
        added = updated = 0
        stamp = _now().isoformat()
        with self._db:
            for r in records:
                row = (r.title, r.description, r.registration_schema,
                       r.date_registered.isoformat() if r.date_registered else None,
                       r.date_modified.isoformat() if r.date_modified else None,
                       _SEP.join(r.subjects), _SEP.join(r.tags), int(r.withdrawn), r.link,
                       r.normalised, stamp)
                exists = self._db.execute("SELECT 1 FROM osf_mirror WHERE id = ?",
                                          (r.id,)).fetchone()
                if exists is None:
                    added += 1
                    self._db.execute(
                        "INSERT INTO osf_mirror (title, description, registration_schema, "
                        "date_registered, date_modified, subjects, tags, withdrawn, link, "
                        "normalised, updated_at, id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (*row, r.id))
                    self._db.execute("INSERT INTO osf_fts (id, normalised) VALUES (?, ?)",
                                     (r.id, r.normalised))
                    continue
                updated += 1
                self._db.execute(
                    "UPDATE osf_mirror SET title = ?, description = ?, registration_schema = ?, "
                    "date_registered = COALESCE(?, date_registered), date_modified = ?, "
                    "subjects = ?, tags = ?, withdrawn = ?, link = ?, normalised = ?, "
                    "updated_at = ? WHERE id = ?", (*row, r.id))
                self._db.execute("UPDATE osf_fts SET normalised = ? WHERE id = ?",
                                 (r.normalised, r.id))
        return added, updated

    def log_refresh(self, mode: str, *, covered_to: Optional[date], seen: int, added: int,
                    updated: int, refreshed_at: Optional[datetime] = None) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO osf_refreshes (refreshed_at, mode, covered_to, seen, "
                "records_added, records_updated) VALUES (?, ?, ?, ?, ?, ?)",
                ((refreshed_at or _now()).isoformat(), mode,
                 covered_to.isoformat() if covered_to else None, seen, added, updated))

    # -- reads -------------------------------------------------------------------
    def has(self, registration_id: str) -> bool:
        return self._db.execute("SELECT 1 FROM osf_mirror WHERE id = ?",
                                (registration_id,)).fetchone() is not None

    def record_count(self, *, include_withdrawn: bool = True) -> int:
        where = "" if include_withdrawn else " WHERE withdrawn = 0"
        return self._db.execute(f"SELECT COUNT(*) FROM osf_mirror{where}").fetchone()[0]

    def _refresh(self, order_by: str) -> Optional[RefreshInfo]:
        row = self._db.execute(
            "SELECT refreshed_at, mode, covered_to, records_added, records_updated "
            f"FROM osf_refreshes {order_by} LIMIT 1").fetchone()
        if row is None:
            return None
        return RefreshInfo(datetime.fromisoformat(row[0]), row[1], _date(row[2]), row[3], row[4])

    def last_refresh(self) -> Optional[RefreshInfo]:
        return self._refresh("ORDER BY id DESC")

    def coverage(self) -> Optional[RefreshInfo]:
        return self._refresh("WHERE covered_to IS NOT NULL ORDER BY covered_to DESC, id DESC")

    def ensure_fresh(self, *, max_age_days: int, today: Optional[date] = None) -> RefreshInfo:
        """Refuse to proceed on a stale mirror, as for PROSPERO."""
        today = today or _now().date()
        info = self.coverage()
        if info is None or info.covered_to is None:
            raise StaleMirrorError("The OSF mirror has never been refreshed: run "
                                   "`osf harvest` before checking candidates.")
        age = (today - info.covered_to).days
        if age > max_age_days:
            raise StaleMirrorError(
                f"The OSF mirror is {age} days old (covers registrations to "
                f"{info.covered_to}; limit {max_age_days} days). Run `osf refresh`.")
        return info

    def _matches(self, rows) -> list[OsfMatch]:
        return [OsfMatch(r[0], r[1], r[2], r[3] or "", _date(r[4]), r[5], r[6]) for r in rows]

    def search(self, text: str, *, limit: int = 50,
               registered_before: Optional[date] = None) -> list[OsfMatch]:
        """Registrations sharing words with `text`, best bm25 first (withdrawn left out).

        `registered_before` restricts to registrations before a cutoff (backtests)."""
        terms = sorted(set(match_key(text).split()))
        if not terms:
            return []
        cutoff = " AND m.date_registered < ?" if registered_before else ""
        args: list = [" OR ".join(f'"{t}"' for t in terms)]
        if registered_before:
            args.append(registered_before.isoformat())
        rows = self._db.execute(
            "SELECT m.id, m.title, m.description, m.registration_schema, m.date_registered, "
            "m.link, bm25(osf_fts) FROM osf_fts f JOIN osf_mirror m ON m.id = f.id "
            f"WHERE osf_fts MATCH ? AND m.withdrawn = 0{cutoff} ORDER BY bm25(osf_fts) LIMIT ?",
            (*args, limit)).fetchall()
        return self._matches(rows)

    def get(self, ids: list[str]) -> list[OsfMatch]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = self._db.execute(
            "SELECT id, title, description, registration_schema, date_registered, link, 0 "
            f"FROM osf_mirror WHERE id IN ({marks})", ids).fetchall()
        return self._matches(rows)

    def texts(self, *, include_withdrawn: bool = False) -> dict[str, str]:
        """{id: title and description}, for the semantic index."""
        where = "" if include_withdrawn else " WHERE withdrawn = 0"
        return {r[0]: f"{r[1]}. {r[2]}" for r in
                self._db.execute(f"SELECT id, title, description FROM osf_mirror{where}")}
