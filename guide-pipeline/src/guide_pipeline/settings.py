"""Configuration for the guide pipeline.

All gate thresholds and limits live here as *settings* (env-overridable), never
hardcoded at their call sites — see CLAUDE.md and the Step 3 gates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # loading a local .env is convenient but never required
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    pass


def _get(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    value = _get(name)
    return int(value) if value is not None else default


def _get_float(name: str, default: float) -> float:
    value = _get(name)
    return float(value) if value is not None else default


@dataclass(frozen=True)
class Thresholds:
    """Step 3 gate thresholds. Settings, not hardcoded (see CLAUDE.md)."""

    min_eligible_studies: int = 8               # fewer than this is too few to pool
    scoping_min_studies: int = 5                # ...downgrade to scoping/narrative down to this
    max_records_to_screen: int = 400            # reject above this to screen (team of 2; scales)
    recent_review_years: int = 4                # reject if an SR/MA exists within N years (3-5)
    active_trial_completion_months: int = 12    # flag trials due to complete within N months
    candidate_titles_min: int = 8               # LLM generates this many candidate titles...
    candidate_titles_max: int = 12              # ...up to this many, across the 14 axes
    candidate_min_axes: int = 6                 # a batch must span at least this many axes
    candidate_max_per_axis: int = 2             # ...with no more than this many from one axis
    max_candidate_batches: int = 3              # new batches while none pass, up to this many
    # Calibrated on the full mirror (2026-09-25): light rewordings of registered
    # titles score ~0.80; true duplicates reworded more heavily and genuinely
    # different close questions overlap at ~0.55-0.70; different questions on
    # the same topic ~0.40-0.50. So only obvious rewordings auto-reject; the
    # overlap band goes to a human.
    prospero_reject_similarity: float = 0.75    # a registered title this similar rejects
    prospero_review_similarity: float = 0.45    # ...this similar is surfaced for human review

    @classmethod
    def from_env(cls) -> "Thresholds":
        return cls(
            min_eligible_studies=_get_int("MIN_ELIGIBLE_STUDIES", 8),
            scoping_min_studies=_get_int("SCOPING_MIN_STUDIES", 5),
            max_records_to_screen=_get_int("MAX_RECORDS_TO_SCREEN", 400),
            recent_review_years=_get_int("RECENT_REVIEW_YEARS", 4),
            active_trial_completion_months=_get_int("ACTIVE_TRIAL_COMPLETION_MONTHS", 12),
            candidate_titles_min=_get_int("CANDIDATE_TITLES_MIN", 8),
            candidate_titles_max=_get_int("CANDIDATE_TITLES_MAX", 12),
            candidate_min_axes=_get_int("CANDIDATE_MIN_AXES", 6),
            candidate_max_per_axis=_get_int("CANDIDATE_MAX_PER_AXIS", 2),
            max_candidate_batches=_get_int("MAX_CANDIDATE_BATCHES", 3),
            prospero_reject_similarity=_get_float("PROSPERO_REJECT_SIMILARITY", 0.75),
            prospero_review_similarity=_get_float("PROSPERO_REVIEW_SIMILARITY", 0.45),
        )


@dataclass(frozen=True)
class Settings:
    # data-source API access
    ncbi_api_key: Optional[str] = None
    ncbi_tool: str = "symposed-guide-pipeline"
    ncbi_email: Optional[str] = None
    # llm — Claude Sonnet 5 for every task (effort per task); Groq selectable
    llm_provider: str = "anthropic"
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5"
    llm_temperature: float = 0.4
    # step 2 landscape: how many recent years of the publication trend to fetch
    landscape_years: int = 10
    # PROSPERO mirror (spec section 3)
    prospero_db: Path = Path("data/prospero.sqlite")
    prospero_max_age_days: int = 10     # refuse to run on a mirror older than this
    prospero_min_interval: float = 3.0  # seconds between requests to PROSPERO
    # paths
    output_dir: Path = Path("output")
    thresholds: Thresholds = field(default_factory=Thresholds)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            ncbi_api_key=_get("NCBI_API_KEY"),
            ncbi_tool=_get("NCBI_TOOL", "symposed-guide-pipeline") or "symposed-guide-pipeline",
            ncbi_email=_get("NCBI_EMAIL"),
            llm_provider=(_get("LLM_PROVIDER", "anthropic") or "anthropic").lower(),
            groq_api_key=_get("GROQ_API_KEY"),
            groq_model=_get("GROQ_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b",
            anthropic_api_key=_get("ANTHROPIC_API_KEY"),
            anthropic_model=_get("ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
            llm_temperature=float(_get("LLM_TEMPERATURE", "0.4") or "0.4"),
            landscape_years=_get_int("LANDSCAPE_YEARS", 10),
            prospero_db=Path(_get("PROSPERO_DB", "data/prospero.sqlite") or "data/prospero.sqlite"),
            prospero_max_age_days=_get_int("PROSPERO_MAX_AGE_DAYS", 10),
            prospero_min_interval=_get_float("PROSPERO_MIN_INTERVAL", 3.0),
            output_dir=Path(_get("OUTPUT_DIR", "output") or "output"),
            thresholds=Thresholds.from_env(),
        )

    def missing_keys(self) -> list[str]:
        """Required-but-unset keys for the active LLM provider plus NCBI."""
        missing: list[str] = []
        if not self.ncbi_api_key:
            missing.append("NCBI_API_KEY")
        if self.llm_provider == "groq" and not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
