"""Step 2 — concept mapping & research landscape.

Given a proforma topic, produce:
  - the real MeSH descriptors it maps to (from the MeSH database), and
  - four landscape figures, every one a real PubMed count:
      * total literature on the topic,
      * the publication-per-year trend over the recent window,
      * how many existing systematic reviews / meta-analyses there are,
      * how many existing guidelines there are.

The systematic-review and guideline figures use PubMed's own filters, so a human
can immediately see whether the space is already crowded — but nothing here
decides what goes in a review (CLAUDE.md rule 2); it only describes the landscape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .sources.pubmed import MeshTerm, PubMedClient

# PubMed's own filters. `systematic[sb]` is the systematic-review subset;
# guidelines are the two guideline publication types.
FILTER_SYSTEMATIC_REVIEW = "systematic[sb]"
FILTER_GUIDELINE = '(Guideline[ptyp] OR "Practice Guideline"[ptyp])'


@dataclass(frozen=True)
class Landscape:
    topic: str
    mesh_terms: list[MeshTerm]
    total_literature: int
    by_year: dict[int, int]
    systematic_reviews: int
    guidelines: int

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "mesh_terms": [{"name": t.name, "ui": t.ui} for t in self.mesh_terms],
            "total_literature": self.total_literature,
            "by_year": {str(y): n for y, n in self.by_year.items()},
            "systematic_reviews": self.systematic_reviews,
            "guidelines": self.guidelines,
        }


def assess_landscape(
    pubmed: PubMedClient,
    topic: str,
    *,
    years: int = 10,
    current_year: Optional[int] = None,
) -> Landscape:
    """Map `topic` to MeSH terms and gather the four landscape counts."""
    current_year = current_year or datetime.now(timezone.utc).year
    mesh_terms = pubmed.mesh_terms(topic)
    total = pubmed.count(topic)
    by_year = {
        year: pubmed.count(topic, min_year=year, max_year=year)
        for year in range(current_year - years + 1, current_year + 1)
    }
    systematic_reviews = pubmed.count(f"({topic}) AND {FILTER_SYSTEMATIC_REVIEW}")
    guidelines = pubmed.count(f"({topic}) AND {FILTER_GUIDELINE}")
    return Landscape(
        topic=topic,
        mesh_terms=mesh_terms,
        total_literature=total,
        by_year=by_year,
        systematic_reviews=systematic_reviews,
        guidelines=guidelines,
    )
