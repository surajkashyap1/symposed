"""Shared shapes for gap mining v2: a candidate question in PICO form."""

from __future__ import annotations

from dataclasses import asdict, dataclass

PICO_FIELDS = ("population", "intervention", "comparator", "outcomes", "study_designs")


@dataclass(frozen=True)
class Pico:
    population: str
    intervention: str  # intervention or exposure
    comparator: str
    outcomes: str
    study_designs: str

    def as_text(self) -> str:
        return "\n".join(f"{f.replace('_', ' ').capitalize()}: {getattr(self, f) or 'not stated'}"
                         for f in PICO_FIELDS)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Pico":
        return cls(**{f: str(d.get(f, "") or "") for f in PICO_FIELDS})


EMPTY_PICO = Pico("", "", "", "", "")


@dataclass(frozen=True)
class Question:
    """A proposed review. `key` identifies it in the store.

    For an update, `updates` names the existing review it would update and
    `description` holds that review's abstract (its PICO may be left empty).
    """

    key: str
    title: str
    pico: Pico = EMPTY_PICO
    description: str = ""
    updates: str = ""

    @property
    def search_text(self) -> str:
        """What the question is about, in one string, for similarity search."""
        p = self.pico
        return ". ".join(x for x in (self.title, p.population, p.intervention, p.comparator,
                                     p.outcomes, self.description[:1000]) if x)

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "pico": self.pico.as_dict(),
                "updates": self.updates}
