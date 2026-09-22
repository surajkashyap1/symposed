"""Data-source clients (v1): PubMed, Europe PMC, ClinicalTrials.gov.

Every count and record these return is parsed from a real API response — never
supplied by a model (CLAUDE.md rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..http import CachedHttpClient
from ..settings import Settings
from .clinicaltrials import ClinicalTrialsClient
from .europepmc import EuropePmcClient
from .pubmed import MeshTerm, PubMedClient

__all__ = [
    "PubMedClient",
    "MeshTerm",
    "EuropePmcClient",
    "ClinicalTrialsClient",
    "Sources",
    "build_sources",
]

# PubMed: 10 req/s with an API key, 3 without. The others have no published
# hard limit; we stay polite at ~3 req/s.
_PUBMED_INTERVAL_WITH_KEY = 0.1
_PUBMED_INTERVAL_NO_KEY = 0.35
_POLITE_INTERVAL = 0.35


@dataclass(frozen=True)
class Sources:
    """The three v1 data-source clients, ready to query."""

    pubmed: PubMedClient
    europepmc: EuropePmcClient
    clinicaltrials: ClinicalTrialsClient


def build_sources(settings: Settings, *, cache_dir: str | Path = ".cache") -> Sources:
    """Construct all three clients from settings, one HTTP client (and cache) each."""
    cache_dir = Path(cache_dir)
    pubmed_interval = (
        _PUBMED_INTERVAL_WITH_KEY if settings.ncbi_api_key else _PUBMED_INTERVAL_NO_KEY
    )
    return Sources(
        pubmed=PubMedClient(
            http=CachedHttpClient(cache_dir=cache_dir, min_interval=pubmed_interval),
            api_key=settings.ncbi_api_key,
            tool=settings.ncbi_tool,
            email=settings.ncbi_email,
        ),
        europepmc=EuropePmcClient(
            http=CachedHttpClient(cache_dir=cache_dir, min_interval=_POLITE_INTERVAL),
        ),
        clinicaltrials=ClinicalTrialsClient(
            http=CachedHttpClient(cache_dir=cache_dir, min_interval=_POLITE_INTERVAL),
        ),
    )
