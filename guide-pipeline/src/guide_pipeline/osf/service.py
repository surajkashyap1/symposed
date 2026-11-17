"""OSF mirror operations: full harvest once at setup, delta pull before each run.

Same pattern as the PROSPERO mirror. The harvest reads every public
registration a month at a time (by `date_created`) and keeps those that pass
`records.keep`. The delta pull reads everything modified since the mirror was
last current, so new registrations arrive and withdrawals are marked. A window
is merged as it lands, but the refresh is only logged at the end, so the
staleness guard keeps blocking until a harvest completes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from .adapter import OsfError, OsfSource
from .mirror import OsfMirror
from .records import keep

# The oldest public OSF registrations date from 2012 (1,065 before 2014, seen live).
REGISTER_START = date(2012, 1, 1)
# Days re-pulled before the last coverage date; the upsert makes overlap free.
_OVERLAP = timedelta(days=1)
# Split a window when it holds more than this many registrations, so no single
# window pages too deep (OSF has had about 4,000 a month).
WINDOW_MAX = 10_000

Progress = Callable[[str], None]


def _today() -> date:
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class OsfHarvestSummary:
    seen: int     # registrations read from OSF
    kept: int     # ...that passed the filter (or were already in the mirror)
    added: int
    updated: int
    windows: int
    covered_to: Optional[date]


def _month_end(d: date) -> date:
    """The first day of the next month (window ends are exclusive)."""
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _pull(source: OsfSource, mirror: OsfMirror, start: date, end: date, field: str,
          progress: Optional[Progress]) -> tuple[int, int, int, int, int]:
    """Fetch [start, end) by `field`, splitting windows over WINDOW_MAX."""
    seen = kept = added = updated = windows = 0
    pending = [(start, end)]
    while pending:
        lo, hi = pending.pop(0)
        n = source.count_window(lo, hi, field=field)
        if n == 0:
            continue
        if n > WINDOW_MAX and (hi - lo).days > 1:
            mid = lo + (hi - lo) // 2
            pending[:0] = [(lo, mid), (mid, hi)]
            continue
        records = source.fetch_window(lo, hi, field=field)
        # A registration already mirrored is updated even if it no longer passes
        # the filter (e.g. withdrawn, or its description edited).
        chosen = [r for r in records if keep(r) or mirror.has(r.id)]
        a, u = mirror.merge(chosen)
        seen, kept, added, updated, windows = (seen + len(records), kept + len(chosen),
                                               added + a, updated + u, windows + 1)
        if progress:
            progress(f"{lo} to {hi - timedelta(days=1)}: {len(records):,} registrations, "
                     f"{len(chosen):,} kept (+{a:,} new)")
    return seen, kept, added, updated, windows


def full_harvest(source: OsfSource, mirror: OsfMirror, *, start: date = REGISTER_START,
                 end: Optional[date] = None,
                 progress: Optional[Progress] = None) -> OsfHarvestSummary:
    """One-off harvest of every public registration, a month at a time."""
    end = end or _today()
    totals = [0, 0, 0, 0, 0]
    lo = date(start.year, start.month, 1)
    while lo <= end:
        hi = min(_month_end(lo), end + timedelta(days=1))
        for i, v in enumerate(_pull(source, mirror, lo, hi, "date_created", progress)):
            totals[i] += v
        lo = hi
    seen, kept, added, updated, windows = totals
    mirror.log_refresh(source.mode, covered_to=end, seen=seen, added=added, updated=updated)
    return OsfHarvestSummary(seen, kept, added, updated, windows, end)


def delta_refresh(source: OsfSource, mirror: OsfMirror, *, today: Optional[date] = None,
                  progress: Optional[Progress] = None) -> OsfHarvestSummary:
    """Registrations created or changed since the mirror was last current."""
    today = today or _today()
    info = mirror.coverage()
    if info is None or info.covered_to is None:
        raise OsfError("The OSF mirror is empty: run a full harvest first.")
    seen, kept, added, updated, windows = _pull(
        source, mirror, info.covered_to - _OVERLAP, today + timedelta(days=1),
        "date_modified", progress)
    mirror.log_refresh(source.mode, covered_to=today, seen=seen, added=added, updated=updated)
    return OsfHarvestSummary(seen, kept, added, updated, windows, today)
