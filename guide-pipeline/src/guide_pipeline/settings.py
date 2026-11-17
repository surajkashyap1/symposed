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
    heterogeneity_max_outcomes: int = 5         # flag above this many distinct primary outcomes
    workable_min_studies: int = 12              # Stage 4b: eligible studies in the workable band...
    workable_max_studies: int = 40              # ...score highest
    recency_years: int = 5                      # "recent" evidence for the recency score
    score_margin: float = 0.05                  # leader must win by more than this to go alone
    max_tied: int = 3                           # at most this many tied go to deep retrieval
    max_preprints: int = 50                     # Europe PMC preprints added to retrieval
    prospero_reject_similarity: float = 0.75    # a registered title this similar rejects
    prospero_review_similarity: float = 0.45    # ...this similar is surfaced for human review
    # Review led discovery (guide v2, step 3)
    review_years: int = 10                      # neighbouring reviews: the last N years
    max_fulltexts: int = 6                      # reviews read per topic (each is a download)
    final_check_reviews: int = 3                # reviews read for the final novelty check
    # Reviews of any kind (narrative included) in the last N years. Narrow
    # clinical topics often have 100 to 200 (seen live: SGLT2 inhibitors in
    # transplant recipients, 150), a whole field thousands (SGLT2 inhibitors, 6,365).
    topic_max_reviews: int = 300                # a topic with more is too broad
    topic_min_primary: int = 30                 # primary studies a topic needs (last N years)
    max_topics: int = 8                         # topics proposed for a vague request
    # Journal novelty check before a question reaches the shortlist (novelty.py)
    novelty_reviews: int = 6                    # closest reviews of any kind, any type
    novelty_primary: int = 8                    # closest recent primary studies
    novelty_primary_years: int = 6              # ...from the last N years
    novelty_per_topic: int = 4                  # questions checked per topic read
    novelty_max_checks: int = 15                # questions checked in one request, at most

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
            heterogeneity_max_outcomes=_get_int("HETEROGENEITY_MAX_OUTCOMES", 5),
            workable_min_studies=_get_int("WORKABLE_MIN_STUDIES", 12),
            workable_max_studies=_get_int("WORKABLE_MAX_STUDIES", 40),
            recency_years=_get_int("RECENCY_YEARS", 5),
            score_margin=_get_float("SCORE_MARGIN", 0.05),
            max_tied=_get_int("MAX_TIED", 3),
            max_preprints=_get_int("MAX_PREPRINTS", 50),
            prospero_reject_similarity=_get_float("PROSPERO_REJECT_SIMILARITY", 0.75),
            prospero_review_similarity=_get_float("PROSPERO_REVIEW_SIMILARITY", 0.45),
            review_years=_get_int("REVIEW_YEARS", 10),
            max_fulltexts=_get_int("MAX_FULLTEXTS", 6),
            final_check_reviews=_get_int("FINAL_CHECK_REVIEWS", 3),
            topic_max_reviews=_get_int("TOPIC_MAX_REVIEWS", 300),
            topic_min_primary=_get_int("TOPIC_MIN_PRIMARY", 30),
            max_topics=_get_int("MAX_TOPICS", 8),
            novelty_reviews=_get_int("NOVELTY_REVIEWS", 6),
            novelty_primary=_get_int("NOVELTY_PRIMARY", 8),
            novelty_primary_years=_get_int("NOVELTY_PRIMARY_YEARS", 6),
            novelty_per_topic=_get_int("NOVELTY_PER_TOPIC", 4),
            novelty_max_checks=_get_int("NOVELTY_MAX_CHECKS", 15),
        )


def _get_bool(name: str, default: bool) -> bool:
    value = _get(name)
    return default if value is None else value.lower() in ("1", "true", "yes", "on")



@dataclass(frozen=True)
class UpdateConfig:
    """The update pipeline (docs/spec-update-pipeline.md, Samarth 2026-10-25)."""

    # Step 3 checks reviews in batches and stops once this many pass both filters
    # (Samarth, 2026-10-29: 30), then hands them to Step 3b.
    review_count: int = 30
    review_batch: int = 25              # step 3: reviews novelty checked per batch
    review_pool_factor: int = 3         # step 3: reviews drawn per review needed, at most
    # A request with no topic draws reviews at random from the whole literature,
    # published from this year to the 3 year cutoff.
    blank_topic_since_year: int = 2000
    review_min_age_years: int = 3       # step 3: published more than this many years ago
    # Step 3, optional: of the reviews found, keep only those certainly older than
    # this many years (0 = no extra filter), then a fixed random sample of at most
    # this many (0 = keep all). Samarth, 2026-10-25: 30 reviews over 5 years old.
    review_sample_min_age_years: int = 0
    review_sample: int = 0
    # Reviews named by a person (REVIEW_PMIDS=1,2,3): step 3 is skipped for them.
    review_pmids: tuple[str, ...] = ()
    overlap_retrieval_k: int = 30       # step 3: later records the judge compares per review
    max_hits: int = 3000                # step 5: a search returning more is too broad to screen
    min_new_eligible: int = 6           # step 5: "more than 5" new eligible studies (marked only)
    run_budget_usd: float = 50.0        # step 5: pause before screening would cost more than this
    search_recall_min: float = 0.90     # step 7: share of the original's studies the search finds
    screen_recall_min: float = 0.95     # step 7: ...and screening keeps
    max_search_revisions: int = 2       # step 7: revisions after a failed recall test
    # The two agentic filters (Samarth, 2026-10-27): Step 3b triage before full
    # texts are asked for, Step 5b appraisal once they are in. Their prompts are
    # read from AGENT_PROMPTS_DIR on every run.
    target_eligible_min: int = 10       # a feasible review has at least this many eligible studies
    target_eligible_max: int = 60       # ...and at most this many
    max_calls_per_candidate: int = 8    # Step 3b tool calls per candidate review
    max_calls_per_option: int = 15      # Step 5b tool calls per shortlisted option
    full_screen_max: int = 300          # Step 5b: screen every record at or below this many
    sample_size: int = 50               # Step 5b: otherwise screen a sample of at least this many
    stage_budget_usd: float = 25.0      # each stage stops when its model spend passes this

    @classmethod
    def from_env(cls) -> "UpdateConfig":
        d = cls()
        return cls(
            review_count=_get_int("REVIEW_COUNT", d.review_count),
            review_batch=_get_int("REVIEW_BATCH", d.review_batch),
            review_pool_factor=_get_int("REVIEW_POOL_FACTOR", d.review_pool_factor),
            blank_topic_since_year=_get_int("BLANK_TOPIC_SINCE_YEAR", d.blank_topic_since_year),
            review_min_age_years=_get_int("REVIEW_MIN_AGE_YEARS", d.review_min_age_years),
            review_sample_min_age_years=_get_int("REVIEW_SAMPLE_MIN_AGE_YEARS",
                                                 d.review_sample_min_age_years),
            review_sample=_get_int("REVIEW_SAMPLE", d.review_sample),
            review_pmids=tuple(p.strip() for p in (_get("REVIEW_PMIDS", "") or "").split(",")
                               if p.strip()),
            overlap_retrieval_k=_get_int("OVERLAP_RETRIEVAL_K", d.overlap_retrieval_k),
            max_hits=_get_int("MAX_HITS", d.max_hits),
            min_new_eligible=_get_int("MIN_NEW_ELIGIBLE", d.min_new_eligible),
            run_budget_usd=_get_float("RUN_BUDGET_USD", d.run_budget_usd),
            search_recall_min=_get_float("SEARCH_RECALL_MIN", d.search_recall_min),
            screen_recall_min=_get_float("SCREEN_RECALL_MIN", d.screen_recall_min),
            max_search_revisions=_get_int("MAX_SEARCH_REVISIONS", d.max_search_revisions),
            target_eligible_min=_get_int("TARGET_ELIGIBLE_MIN", d.target_eligible_min),
            target_eligible_max=_get_int("TARGET_ELIGIBLE_MAX", d.target_eligible_max),
            max_calls_per_candidate=_get_int("MAX_CALLS_PER_CANDIDATE",
                                             d.max_calls_per_candidate),
            max_calls_per_option=_get_int("MAX_CALLS_PER_OPTION", d.max_calls_per_option),
            full_screen_max=_get_int("FULL_SCREEN_MAX", d.full_screen_max),
            sample_size=_get_int("SAMPLE_SIZE", d.sample_size),
            stage_budget_usd=_get_float("STAGE_BUDGET_USD", d.stage_budget_usd),
        )


CANDIDATE_SOURCES = ("updates", "generated")
# Models allowed to run the two agentic filters: Claude Opus 5.5 or more capable.
AGENT_MODELS = ("claude-opus-5-5", "claude-fable-5-1", "claude-fable-5", "claude-mythos-5-1")


@dataclass(frozen=True)
class Settings:
    # data-source API access
    ncbi_api_key: Optional[str] = None
    ncbi_tool: str = "symposed-guide-pipeline"
    ncbi_email: Optional[str] = None
    # Contact for OpenAlex / Crossref "polite pools". Deliberately separate from
    # NCBI_EMAIL, which is a personal address given for NCBI only.
    contact_email: Optional[str] = None
    # llm — two Claude models (see llm.DECISION_TASKS); Groq selectable
    llm_provider: str = "anthropic"
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5-5"          # the reader
    anthropic_decision_model: str = "claude-opus-5-5"   # the decider
    anthropic_fast_model: str = "claude-haiku-5-5"      # quick tasks (llm.FAST_TASKS)
    llm_fallbacks: bool = True  # server side refusal fallback on synchronous calls
    llm_temperature: float = 0.4
    # step 2 landscape: how many recent years of the publication trend to fetch
    landscape_years: int = 10
    # screening (Stage 5 v2)
    llm_concurrency: int = 4            # papers screened in parallel (sync mode)
    llm_batch: bool = True              # per-paper steps via the Batch API (half price)
    batch_poll_seconds: float = 30.0    # how often to check a running batch
    fulltext_max_chars: int = 60_000    # cap on open-access full text per paper
    # how candidate questions are found: "reviews" (read neighbouring reviews and
    # mine their gaps, guide v2) or "axes" (the 14 gap axes, the v1 method)
    discovery_mode: str = "reviews"
    # stop after scoring with a shortlist of the top 3 questions and write the
    # guide only once a person picks one (`pick` command), Samarth 2026-10-18
    pick_before_guide: bool = True
    # website database the pipeline reads orders from and writes runs to
    database_url: Optional[str] = None
    # PROSPERO mirror (spec section 3)
    prospero_db: Path = Path("data/prospero.sqlite")
    prospero_max_age_days: int = 10     # refuse to run on a mirror older than this
    prospero_min_interval: float = 3.0  # seconds between requests to PROSPERO
    # "updates" finds systematic reviews due an update (docs/spec-update-pipeline.md);
    # "generated" is the earlier pipeline (review led or axes discovery), kept.
    candidate_source: str = "updates"
    # Testing runs may leave out the PROSPERO and OSF checks to save time
    # (Samarth, 2026-10-24). Every output then says the registries were not checked.
    skip_registry_mirrors: bool = False
    # Testing only: PROSPERO checked, OSF not (its copy is still downloading).
    skip_osf_mirror: bool = False
    # Steps 3b and 5b on a safety-classifier refusal (Samarth, 2026-10-30: allowed after a
    # false "bio" decline on abortion and transgender health topics). Empty = off,
    # "default" = Anthropic's choice of fallback model, or a comma list of models.
    agent_refusal_fallback: str = ""
    # The delivered guide is a read-only Word document (Samarth, 2026-11-17). A password
    # stops readers switching the protection off. A PDF copy is optional, made by Word.
    guide_password: str = ""
    guide_pdf: bool = False
    # OSF registrations mirror, same pattern as PROSPERO
    osf_db: Path = Path("data/osf.sqlite")
    osf_min_interval: float = 1.0       # seconds between requests to the OSF API
    osf_token: Optional[str] = None     # personal access token, only if rate limits bite
    mirror_staleness_days: int = 10     # the OSF guard (PROSPERO keeps its own setting)
    # Overlap judgements, kept permanently (local SQLite for now)
    mining_db: Path = Path("data/mining.sqlite")
    # Local open source embedding model for overlap retrieval (no API cost)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    vectors_db: Path = Path("data/vectors.sqlite")
    models_dir: Path = Path("data/models")
    # The Step 3b and Step 5b prompts (markdown, edited by hand, read every run).
    agent_prompts_dir: Path = Path(__file__).resolve().parent / "prompts"
    # paths
    output_dir: Path = Path("output")
    thresholds: Thresholds = field(default_factory=Thresholds)
    updates: UpdateConfig = field(default_factory=UpdateConfig)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            ncbi_api_key=_get("NCBI_API_KEY"),
            ncbi_tool=_get("NCBI_TOOL", "symposed-guide-pipeline") or "symposed-guide-pipeline",
            ncbi_email=_get("NCBI_EMAIL"),
            contact_email=_get("CONTACT_EMAIL"),
            llm_provider=(_get("LLM_PROVIDER", "anthropic") or "anthropic").lower(),
            groq_api_key=_get("GROQ_API_KEY"),
            groq_model=_get("GROQ_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b",
            anthropic_api_key=_get("ANTHROPIC_API_KEY"),
            anthropic_model=_get("ANTHROPIC_MODEL", "claude-sonnet-5-5") or "claude-sonnet-5-5",
            anthropic_fast_model=_get("ANTHROPIC_FAST_MODEL", "claude-haiku-5-5")
            or "claude-haiku-5-5",
            anthropic_decision_model=(_get("ANTHROPIC_DECISION_MODEL", "claude-opus-5-5")
                                      or "claude-opus-5-5"),
            llm_fallbacks=(_get("LLM_FALLBACKS", "true") or "true").lower()
            in ("1", "true", "yes", "on"),
            llm_temperature=float(_get("LLM_TEMPERATURE", "0.4") or "0.4"),
            landscape_years=_get_int("LANDSCAPE_YEARS", 10),
            llm_concurrency=_get_int("LLM_CONCURRENCY", 4),
            llm_batch=(_get("LLM_BATCH", "true") or "true").lower() in ("1", "true", "yes", "on"),
            batch_poll_seconds=_get_float("BATCH_POLL_SECONDS", 30.0),
            fulltext_max_chars=_get_int("FULLTEXT_MAX_CHARS", 60_000),
            discovery_mode=(_get("DISCOVERY_MODE", "reviews") or "reviews").lower(),
            pick_before_guide=(_get("PICK_BEFORE_GUIDE", "true") or "true").lower()
            in ("1", "true", "yes", "on"),
            database_url=_get("PIPELINE_DATABASE_URL") or _get("STAGING_DATABASE_URL"),
            prospero_db=Path(_get("PROSPERO_DB", "data/prospero.sqlite") or "data/prospero.sqlite"),
            prospero_max_age_days=_get_int("PROSPERO_MAX_AGE_DAYS", 10),
            prospero_min_interval=_get_float("PROSPERO_MIN_INTERVAL", 3.0),
            candidate_source=(_get("CANDIDATE_SOURCE", "updates") or "updates").lower(),
            skip_registry_mirrors=_get_bool("SKIP_REGISTRY_MIRRORS", False),
            skip_osf_mirror=_get_bool("SKIP_OSF_MIRROR", False),
            agent_refusal_fallback=(_get("AGENT_REFUSAL_FALLBACK", "") or "").strip(),
            guide_password=_get("GUIDE_PASSWORD", "") or "",
            guide_pdf=_get_bool("GUIDE_PDF", False),
            osf_db=Path(_get("OSF_DB", "data/osf.sqlite") or "data/osf.sqlite"),
            osf_min_interval=_get_float("OSF_MIN_INTERVAL", 1.0),
            osf_token=_get("OSF_TOKEN"),
            mirror_staleness_days=_get_int("MIRROR_STALENESS_DAYS", 10),
            mining_db=Path(_get("MINING_DB", "data/mining.sqlite") or "data/mining.sqlite"),
            embedding_model=_get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
            or "BAAI/bge-small-en-v1.5",
            vectors_db=Path(_get("VECTORS_DB", "data/vectors.sqlite") or "data/vectors.sqlite"),
            models_dir=Path(_get("MODELS_DIR", "data/models") or "data/models"),
            agent_prompts_dir=Path(_get("AGENT_PROMPTS_DIR", "")
                                   or Path(__file__).resolve().parent / "prompts"),
            output_dir=Path(_get("OUTPUT_DIR", "output") or "output"),
            thresholds=Thresholds.from_env(),
            updates=UpdateConfig.from_env(),
        )

    def check(self) -> None:
        """Refuse settings that contradict each other."""
        if self.candidate_source not in CANDIDATE_SOURCES:
            raise ValueError(f"CANDIDATE_SOURCE must be one of {', '.join(CANDIDATE_SOURCES)}")
        if self.candidate_source == "updates" and not self.anthropic_decision_model.startswith(
                AGENT_MODELS):
            # The stage prompts: "claude-opus-5-5 or higher. Do not fall back to a
            # smaller model for this stage."
            raise ValueError(f"ANTHROPIC_DECISION_MODEL runs the Step 3b and Step 5b filters and "
                             f"must be one of {', '.join(AGENT_MODELS)}, not "
                             f"{self.anthropic_decision_model}")

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
