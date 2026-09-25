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
    assert settings.anthropic_model == "claude-sonnet-5"
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
