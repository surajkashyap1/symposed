"""The local PROSPERO mirror: storage, merge, refresh log, staleness guard, search.

SQLite with an FTS5 index on each title's match key. Search pulls a shortlist
of titles sharing words with the query (FTS5, ranked by bm25), then scores each
by trigram similarity so reworded duplicates still surface (spec §3.2).

Tables follow spec §5: `prospero_mirror` and `prospero_refreshes`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .records import ProsperoRecord, match_key, similarity

VIEW_URL = "https://www.crd.york.ac.uk/PROSPERO/view/"
_SHORTLIST = 200  # FTS candidates re-scored by trigram similarity

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prospero_mirror (
    registration_id   TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    match_key         TEXT NOT NULL,
    registration_date TEXT,
    status            TEXT,
    condition         TEXT,
    outcomes          TEXT,
    updated_at        TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS prospero_fts USING fts5(
    registration_id UNINDEXED, match_key
);
CREATE TABLE IF NOT EXISTS prospero_refreshes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    refreshed_at    TEXT NOT NULL,
    mode            TEXT NOT NULL,   -- automated | manual
    covered_to      TEXT,            -- registrations are complete up to this date
    records_added   INTEGER NOT NULL,
    records_updated INTEGER NOT NULL
);
"""


class StaleMirrorError(RuntimeError):
    """The mirror is too old (or empty) to trust for a novelty check."""


@dataclass(frozen=True)
class MergeResult:
    added: int
    updated: int


@dataclass(frozen=True)
class RefreshInfo:
    refreshed_at: datetime
    mode: str
    covered_to: Optional[date]
    added: int
    updated: int


@dataclass(frozen=True)
class ProsperoMatch:
    registration_id: str
    title: str
    registration_date: Optional[date]
    score: float

    @property
    def url(self) -> str:
        return VIEW_URL + self.registration_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _date(text: Optional[str]) -> Optional[date]:
    return date.fromisoformat(text) if text else None


class ProsperoMirror:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # -- writes ------------------------------------------------------------------
    def merge(self, records: Iterable[ProsperoRecord]) -> MergeResult:
        """Upsert records. The same path serves automated pulls and manual uploads."""
        added = updated = 0
        stamp = _now().isoformat()
        with self._db:
            for r in records:
                key = match_key(r.title)
                row = self._db.execute(
                    "SELECT title, registration_date FROM prospero_mirror "
                    "WHERE registration_id = ?",
                    (r.registration_id,),
                ).fetchone()
                reg_date = r.registration_date.isoformat() if r.registration_date else None
                if row is None:
                    added += 1
                    self._db.execute(
                        "INSERT INTO prospero_mirror (registration_id, title, match_key, "
                        "registration_date, status, condition, outcomes, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (r.registration_id, r.title, key, reg_date, r.status,
                         r.condition, r.outcomes, stamp),
                    )
                    self._db.execute(
                        "INSERT INTO prospero_fts (registration_id, match_key) VALUES (?, ?)",
                        (r.registration_id, key),
                    )
                    continue
                if row[0] != r.title or (reg_date and row[1] != reg_date):
                    updated += 1
                # Keep existing optional fields when a source doesn't supply them.
                self._db.execute(
                    "UPDATE prospero_mirror SET title = ?, match_key = ?, "
                    "registration_date = COALESCE(?, registration_date), "
                    "status = COALESCE(?, status), condition = COALESCE(?, condition), "
                    "outcomes = COALESCE(?, outcomes), updated_at = ? "
                    "WHERE registration_id = ?",
                    (r.title, key, reg_date, r.status, r.condition, r.outcomes, stamp,
                     r.registration_id),
                )
                self._db.execute(
                    "UPDATE prospero_fts SET match_key = ? WHERE registration_id = ?",
                    (key, r.registration_id),
                )
        return MergeResult(added=added, updated=updated)

    def log_refresh(
        self,
        mode: str,
        *,
        covered_to: Optional[date],
        added: int,
        updated: int,
        refreshed_at: Optional[datetime] = None,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO prospero_refreshes (refreshed_at, mode, covered_to, "
                "records_added, records_updated) VALUES (?, ?, ?, ?, ?)",
                ((refreshed_at or _now()).isoformat(), mode,
                 covered_to.isoformat() if covered_to else None, added, updated),
            )

    # -- reads -------------------------------------------------------------------
    def record_count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM prospero_mirror").fetchone()[0]

    def _refresh(self, order_by: str) -> Optional[RefreshInfo]:
        row = self._db.execute(
            "SELECT refreshed_at, mode, covered_to, records_added, records_updated "
            f"FROM prospero_refreshes {order_by} LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return RefreshInfo(datetime.fromisoformat(row[0]), row[1], _date(row[2]), row[3], row[4])

    def last_refresh(self) -> Optional[RefreshInfo]:
        """The most recently logged refresh."""
        return self._refresh("ORDER BY id DESC")

    def coverage(self) -> Optional[RefreshInfo]:
        """The refresh reaching furthest forward — how current the mirror is."""
        return self._refresh("WHERE covered_to IS NOT NULL ORDER BY covered_to DESC, id DESC")

    def ensure_fresh(self, *, max_age_days: int, today: Optional[date] = None) -> RefreshInfo:
        """Refuse to proceed on a stale mirror (spec §3.4 staleness guard)."""
        today = today or _now().date()
        info = self.coverage()
        if info is None or info.covered_to is None:
            raise StaleMirrorError(
                "The PROSPERO mirror has never been refreshed — run a full harvest "
                "or import an export before checking titles."
            )
        age = (today - info.covered_to).days
        if age > max_age_days:
            raise StaleMirrorError(
                f"The PROSPERO mirror is {age} days old (covers registrations to "
                f"{info.covered_to}; limit {max_age_days} days). Refresh it before "
                "running the pipeline."
            )
        return info

    def search(
        self, title: str, *, limit: int = 5, review_threshold: float = 0.0
    ) -> list[ProsperoMatch]:
        """Most similar registered titles, best first, scoring >= review_threshold."""
        key = match_key(title)
        terms = sorted(set(key.split()))
        if not terms:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in terms)
        rows = self._db.execute(
            "SELECT m.registration_id, m.title, m.match_key, m.registration_date "
            "FROM prospero_fts f JOIN prospero_mirror m "
            "ON m.registration_id = f.registration_id "
            "WHERE prospero_fts MATCH ? ORDER BY bm25(prospero_fts) LIMIT ?",
            (fts_query, _SHORTLIST),
        ).fetchall()
        scored = [
            ProsperoMatch(rid, t, _date(d), round(similarity(key, mk), 3))
            for rid, t, mk, d in rows
        ]
        scored = [m for m in scored if m.score >= review_threshold]
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:limit]
