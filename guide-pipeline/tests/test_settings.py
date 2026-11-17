from guide_pipeline.settings import Settings, Thresholds

ENV_VARS = [
    "NCBI_API_KEY",
    "NCBI_TOOL",
    "NCBI_EMAIL",
    "LLM_PROVIDER",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "OUTPUT_DIR",
    "MIN_ELIGIBLE_STUDIES",
    "MAX_RECORDS_TO_SCREEN",
    "RECENT_REVIEW_YEARS",
    "ACTIVE_TRIAL_COMPLETION_MONTHS",
    "CANDIDATE_TITLES_MIN",
    "CANDIDATE_TITLES_MAX",
]


def _clear_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch):
    _clear_env(monkeypatch)
    settings = Settings.load()
    assert settings.llm_provider == "anthropic"
    assert settings.anthropic_model == "claude-sonnet-5-5"
    assert settings.ncbi_api_key is None
    assert settings.output_dir.name == "output"
    assert settings.thresholds == Thresholds()


def test_env_populates_keys_and_provider(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NCBI_API_KEY", "ncbi-123")
    monkeypatch.setenv("GROQ_API_KEY", "groq-123")
    monkeypatch.setenv("LLM_PROVIDER", "Anthropic")  # case-insensitive
    settings = Settings.load()
    assert settings.ncbi_api_key == "ncbi-123"
    assert settings.groq_api_key == "groq-123"
    assert settings.llm_provider == "anthropic"


def test_thresholds_override_from_env(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("MAX_RECORDS_TO_SCREEN", "250")
    monkeypatch.setenv("MIN_ELIGIBLE_STUDIES", "10")
    thresholds = Settings.load().thresholds
    assert thresholds.max_records_to_screen == 250
    assert thresholds.min_eligible_studies == 10
    assert thresholds.recent_review_years == 4  # untouched default


def test_missing_keys_for_groq(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    missing = Settings.load().missing_keys()
    assert missing == ["NCBI_API_KEY", "GROQ_API_KEY"]


def test_missing_keys_for_anthropic(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NCBI_API_KEY", "x")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert Settings.load().missing_keys() == ["ANTHROPIC_API_KEY"]


def test_no_missing_keys_when_configured(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NCBI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    assert Settings.load().missing_keys() == []


# -- the update pipeline ------------------------------------------------------
UPDATE_VARS = ["CANDIDATE_SOURCE", "SKIP_REGISTRY_MIRRORS", "REVIEW_COUNT",
               "REVIEW_MIN_AGE_YEARS", "MAX_HITS", "RUN_BUDGET_USD", "MIRROR_STALENESS_DAYS"]


def test_update_pipeline_defaults(monkeypatch):
    for name in UPDATE_VARS:
        monkeypatch.delenv(name, raising=False)
    s = Settings.load()
    assert s.candidate_source == "updates" and not s.skip_registry_mirrors
    u = s.updates
    assert (u.review_count, u.review_min_age_years, u.overlap_retrieval_k) == (30, 3, 30)
    assert (u.review_batch, u.review_pool_factor, u.blank_topic_since_year) == (25, 3, 2000)
    assert (u.max_hits, u.min_new_eligible) == (3000, 6)
    assert (u.search_recall_min, u.screen_recall_min, u.max_search_revisions) == (0.90, 0.95, 2)
    assert s.mirror_staleness_days == 10
    s.check()


def test_update_pipeline_env_overrides(monkeypatch):
    monkeypatch.setenv("REVIEW_COUNT", "80")
    monkeypatch.setenv("SKIP_REGISTRY_MIRRORS", "true")
    s = Settings.load()
    assert s.updates.review_count == 80 and s.skip_registry_mirrors


def test_unknown_candidate_source_is_refused(monkeypatch):
    import pytest

    monkeypatch.setenv("CANDIDATE_SOURCE", "generated")
    Settings.load().check()
    monkeypatch.setenv("CANDIDATE_SOURCE", "invented")
    with pytest.raises(ValueError):
        Settings.load().check()
