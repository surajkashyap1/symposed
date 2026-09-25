"""PROSPERO operations the pipeline and CLI use: harvest, refresh, import, check.

Every route into the mirror goes through `ProsperoMirror.merge`, so an automated
pull and a manual upload are merged identically (spec §3.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .adapter import ProsperoSource
from .mirror import ProsperoMatch, ProsperoMirror
from .records import ProsperoError, match_key, parse_export

# PROSPERO opened for registration in February 2011.
REGISTER_START = date(2011, 1, 1)
# Days re-pulled either side of a delta window: date filters and publication
# dates don't line up exactly, and the upsert makes overlap free.
_OVERLAP = timedelta(days=1)

Progress = Callable[[str], None]


def _today() -> date:
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class HarvestSummary:
    added: int
    updated: int
    windows: int  # exports fetched
    covered_to: Optional[date]


def _harvest_range(
    source: ProsperoSource,
    mirror: ProsperoMirror,
    start: date,
    end: date,
    progress: Optional[Progress],
) -> tuple[int, int, int]:
    """Fetch [start, end] in windows under the export cap, merging each as it lands.

    Merging per window means an interrupted harvest keeps what it fetched, but
    no refresh is logged, so the staleness guard still blocks until it completes.
    """
    added = updated = windows = 0
    pending = [(start, end)]
    while pending:
        lo, hi = pending.pop(0)
        n = source.count_range(lo, hi)
        if n == 0:
            continue
        if n > source.export_cap:
            if lo == hi:  # one day over the cap (a bulk migration date, seen live)
                a, u, w = _harvest_day_by_prefix(source, mirror, lo, n, progress)
                added, updated, windows = added + a, updated + u, windows + w
                continue
            mid = lo + (hi - lo) // 2
            pending[:0] = [(lo, mid), (mid + timedelta(days=1), hi)]
            continue
        result = mirror.merge(source.fetch_range(lo, hi))
        added, updated, windows = added + result.added, updated + result.updated, windows + 1
        if progress:
            progress(f"{lo} to {hi}: {n:,} records (+{result.added:,} new)")
    return added, updated, windows


def _harvest_day_by_prefix(
    source: ProsperoSource,
    mirror: ProsperoMirror,
    day: date,
    total: int,
    progress: Optional[Progress],
) -> tuple[int, int, int]:
    """Split one oversized day by accession-number prefix (CRD4, CRD42, ...).

    Every PROSPERO ID starts "CRD" followed by digits, so the prefixes partition
    the day exactly; the counts are checked to add up so nothing is missed.
    """
    chunks: list[tuple[str, int]] = []
    pending = [("CRD", total)]
    while pending:
        prefix, n = pending.pop(0)
        if n <= source.export_cap:
            chunks.append((prefix, n))
            continue
        children = [(prefix + d, source.count_range(day, day, prefix + d)) for d in "0123456789"]
        if sum(c for _, c in children) != n:
            raise ProsperoError(
                f"splitting {day} by ID prefix {prefix}: digits account for "
                f"{sum(c for _, c in children)} of {n} records"
            )
        pending[:0] = [(p, c) for p, c in children if c > 0]
    added = updated = 0
    for prefix, n in chunks:
        result = mirror.merge(source.fetch_range(day, day, prefix))
        added, updated = added + result.added, updated + result.updated
        if progress:
            progress(f"{day} IDs {prefix}*: {n:,} records (+{result.added:,} new)")
    return added, updated, len(chunks)


def full_harvest(
    source: ProsperoSource,
    mirror: ProsperoMirror,
    *,
    start: date = REGISTER_START,
    end: Optional[date] = None,
    progress: Optional[Progress] = None,
) -> HarvestSummary:
    """One-off harvest of the whole register, a year at a time (split as needed)."""
    end = end or _today()
    added = updated = windows = 0
    year_start = start
    while year_start <= end:
        year_end = min(date(year_start.year, 12, 31), end)
        a, u, w = _harvest_range(source, mirror, year_start, year_end, progress)
        added, updated, windows = added + a, updated + u, windows + w
        year_start = year_end + timedelta(days=1)
    mirror.log_refresh(source.mode, covered_to=end, added=added, updated=updated)
    return HarvestSummary(added, updated, windows, end)


def delta_refresh(
    source: ProsperoSource,
    mirror: ProsperoMirror,
    *,
    today: Optional[date] = None,
    progress: Optional[Progress] = None,
) -> HarvestSummary:
    """Pull registrations since the mirror was last current (the weekly refresh)."""
    today = today or _today()
    info = mirror.coverage()
    if info is None or info.covered_to is None:
        raise ProsperoError("The mirror is empty — run a full harvest first.")
    added, updated, windows = _harvest_range(
        source, mirror, info.covered_to - _OVERLAP, today + _OVERLAP, progress
    )
    mirror.log_refresh(source.mode, covered_to=today, added=added, updated=updated)
    return HarvestSummary(added, updated, windows, today)


def import_export_file(path: str | Path, mirror: ProsperoMirror) -> HarvestSummary:
    """Manual fallback: merge an export an administrator downloaded by hand.

    The mirror counts as current only up to the newest registration in the
    file — an old export can't make a stale mirror look fresh.
    """
    records = parse_export(Path(path).read_text(encoding="utf-8-sig"))
    if not records:
        raise ProsperoError(f"No PROSPERO records found in {path}")
    result = mirror.merge(records)
    dates = [r.registration_date for r in records if r.registration_date]
    covered_to = max(dates) if dates else None
    mirror.log_refresh("manual", covered_to=covered_to, added=result.added, updated=result.updated)
    return HarvestSummary(result.added, result.updated, 1, covered_to)


@dataclass(frozen=True)
class ProsperoCheck:
    """The record kept against a request (spec §3.5) — retain permanently."""

    title: str
    search_terms: str
    checked_on: date
    mirror_covered_to: date
    mirror_refreshed_at: datetime
    verdict: str  # registered | review | clear
    matches: list[ProsperoMatch]

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "search_terms": self.search_terms,
            "checked_on": self.checked_on.isoformat(),
            "mirror_covered_to": self.mirror_covered_to.isoformat(),
            "mirror_refreshed_at": self.mirror_refreshed_at.isoformat(),
            "verdict": self.verdict,
            "matches": [
                {
                    "registration_id": m.registration_id,
                    "title": m.title,
                    "registration_date": (
                        m.registration_date.isoformat() if m.registration_date else None
                    ),
                    "score": m.score,
                    "url": m.url,
                }
                for m in self.matches
            ],
        }


def check_title(
    mirror: ProsperoMirror,
    title: str,
    *,
    max_age_days: int,
    reject_threshold: float,
    review_threshold: float,
    today: Optional[date] = None,
    limit: int = 5,
) -> ProsperoCheck:
    """Fuzzy-check a candidate title against the mirror (refuses if stale).

    `registered`: a registered title is similar enough to reject the candidate.
    `review`: near matches a human should look at. `clear`: nothing close.
    """
    today = today or _today()
    info = mirror.ensure_fresh(max_age_days=max_age_days, today=today)
    matches = mirror.search(title, limit=limit, review_threshold=review_threshold)
    if matches and matches[0].score >= reject_threshold:
        verdict = "registered"
    elif matches:
        verdict = "review"
    else:
        verdict = "clear"
    return ProsperoCheck(
        title=title,
        search_terms=match_key(title),
        checked_on=today,
        mirror_covered_to=info.covered_to,
        mirror_refreshed_at=info.refreshed_at,
        verdict=verdict,
        matches=matches,
    )
