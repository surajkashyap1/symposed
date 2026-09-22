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


@dataclass(frozen=True)
class Thresholds:
    """Step 3 gate thresholds. Settings, not hardcoded (see CLAUDE.md)."""

    min_eligible_studies: int = 8               # reject below this many eligible studies
    max_records_to_screen: int = 400            # reject if more than this to screen
    recent_review_years: int = 4                # reject if an SR/MA exists within N years (3-5)
    active_trial_completion_months: int = 12    # reject if an active trial completes within N months
    candidate_titles_min: int = 8               # LLM generates this many candidate titles...
    candidate_titles_max: int = 12              # ...up to this many, across the 14 axes

    @classmethod
    def from_env(cls) -> "Thresholds":
        return cls(
            min_eligible_studies=_get_int("MIN_ELIGIBLE_STUDIES", 8),
            max_records_to_screen=_get_int("MAX_RECORDS_TO_SCREEN", 400),
            recent_review_years=_get_int("RECENT_REVIEW_YEARS", 4),
            active_trial_completion_months=_get_int("ACTIVE_TRIAL_COMPLETION_MONTHS", 12),
            candidate_titles_min=_get_int("CANDIDATE_TITLES_MIN", 8),
            candidate_titles_max=_get_int("CANDIDATE_TITLES_MAX", 12),
        )


@dataclass(frozen=True)
class Settings:
    # data-source API access
    ncbi_api_key: Optional[str] = None
    ncbi_tool: str = "symposed-guide-pipeline"
    ncbi_email: Optional[str] = None
    # llm — Groq first, switchable to Anthropic with no code change
    llm_provider: str = "groq"
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    # step 2 landscape: how many recent years of the publication trend to fetch
    landscape_years: int = 10
    # paths
    output_dir: Path = Path("output")
    thresholds: Thresholds = field(default_factory=Thresholds)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            ncbi_api_key=_get("NCBI_API_KEY"),
            ncbi_tool=_get("NCBI_TOOL", "symposed-guide-pipeline") or "symposed-guide-pipeline",
            ncbi_email=_get("NCBI_EMAIL"),
            llm_provider=(_get("LLM_PROVIDER", "groq") or "groq").lower(),
            groq_api_key=_get("GROQ_API_KEY"),
            anthropic_api_key=_get("ANTHROPIC_API_KEY"),
            landscape_years=_get_int("LANDSCAPE_YEARS", 10),
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
