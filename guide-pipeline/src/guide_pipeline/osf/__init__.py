"""OSF registrations: a local mirror of health evidence synthesis registrations.

Step 3 of the update pipeline checks OSF as well as PROSPERO for an update
already under way, since many reviews are registered there instead. The
pipeline uses only this package's public names; how the data is acquired is
isolated in `adapter.py`, as for PROSPERO.
"""

from .adapter import ApiSource, OsfError, OsfSource
from .mirror import OsfMatch, OsfMirror
from .records import OsfRecord, keep, parse_registration
from .service import OsfHarvestSummary, delta_refresh, full_harvest

__all__ = [
    "ApiSource",
    "OsfError",
    "OsfHarvestSummary",
    "OsfMatch",
    "OsfMirror",
    "OsfRecord",
    "OsfSource",
    "delta_refresh",
    "full_harvest",
    "keep",
    "parse_registration",
]
