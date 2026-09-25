"""PROSPERO: registered-protocol checks against a local mirror (spec §3).

The pipeline uses only this package's public names. How the data is acquired is
isolated in `adapter.py`, so a proper CRD feed would replace one file.
"""

from .adapter import EXPORT_CAP, EndpointSource, ProsperoSource
from .mirror import (
    MergeResult,
    ProsperoMatch,
    ProsperoMirror,
    RefreshInfo,
    StaleMirrorError,
)
from .records import (
    ProsperoError,
    ProsperoRecord,
    match_key,
    parse_export,
    similarity,
)
from .service import (
    HarvestSummary,
    ProsperoCheck,
    check_title,
    delta_refresh,
    full_harvest,
    import_export_file,
)

__all__ = [
    "EXPORT_CAP",
    "EndpointSource",
    "HarvestSummary",
    "MergeResult",
    "ProsperoCheck",
    "ProsperoError",
    "ProsperoMatch",
    "ProsperoMirror",
    "ProsperoRecord",
    "ProsperoSource",
    "RefreshInfo",
    "StaleMirrorError",
    "check_title",
    "delta_refresh",
    "full_harvest",
    "import_export_file",
    "match_key",
    "parse_export",
    "similarity",
]
