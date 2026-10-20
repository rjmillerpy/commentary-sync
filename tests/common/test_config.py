import pytest
from pydantic import ValidationError

from app.common.config import MatcherSettings, Settings

DATABASE_URL = "postgresql+psycopg://commentary:hunter2@db:5432/commentary"
CACHE_URL = "redis://:hunter2@cache:6379/0"
AUTH_SECRET = "hunter2-hunter2-hunter2-hunter2-hunter2"
LIVEKIT_URL = "wss://livekit.example.com"
LIVEKIT_API_KEY = "APIkey"
LIVEKIT_API_SECRET = "hunter2-livekit-hunter2-livekit-hunter2"


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("COMMENTARY_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("COMMENTARY_CACHE_URL", CACHE_URL)
    monkeypatch.setenv("COMMENTARY_AUTH_SECRET", AUTH_SECRET)
    monkeypatch.setenv("COMMENTARY_LIVEKIT_URL", LIVEKIT_URL)
    monkeypatch.setenv("COMMENTARY_LIVEKIT_API_KEY", LIVEKIT_API_KEY)
    monkeypatch.setenv("COMMENTARY_LIVEKIT_API_SECRET", LIVEKIT_API_SECRET)
    return monkeypatch


def build_settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "database_url": DATABASE_URL,
            "cache_url": CACHE_URL,
            "auth_secret": AUTH_SECRET,
            "livekit_url": LIVEKIT_URL,
            "livekit_api_key": LIVEKIT_API_KEY,
            "livekit_api_secret": LIVEKIT_API_SECRET,
            **overrides,
        }
    )


def test_reads_prefixed_environment_variables(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("COMMENTARY_LOG_LEVEL", "DEBUG")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.database_url.get_secret_value() == DATABASE_URL
    assert settings.cache_url.get_secret_value() == CACHE_URL
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    "missing",
    [
        "COMMENTARY_DATABASE_URL",
        "COMMENTARY_CACHE_URL",
        "COMMENTARY_AUTH_SECRET",
        "COMMENTARY_LIVEKIT_URL",
        "COMMENTARY_LIVEKIT_API_KEY",
        "COMMENTARY_LIVEKIT_API_SECRET",
    ],
    ids=["database", "cache", "auth-secret", "livekit-url", "livekit-key", "livekit-secret"],
)
def test_refuses_to_start_without_a_secret(environment: pytest.MonkeyPatch, missing: str) -> None:
    environment.delenv(missing)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_rejects_a_short_auth_secret() -> None:
    with pytest.raises(ValidationError):
        build_settings(auth_secret="x" * 31)


@pytest.mark.parametrize(
    "overrides",
    [
        {"livekit_api_secret": "x" * 31},
        {"livekit_api_key": ""},
        {"livekit_url": "https://livekit.example.com"},
        {"livekit_token_seconds": 59},
    ],
    ids=["short-secret", "empty-key", "not-a-websocket-url", "token-too-short-lived"],
)
def test_rejects_bad_livekit_settings(overrides: dict[str, str | int]) -> None:
    with pytest.raises(ValidationError):
        build_settings(**overrides)


def test_passwords_stay_out_of_the_repr() -> None:
    """Rule 18: a logged or printed Settings object must not leak credentials."""
    assert "hunter2" not in repr(build_settings())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_connect_timeout_seconds", 2.0),
        ("database_connect_timeout_seconds", 60.0),
        ("database_statement_timeout_seconds", 0.1),
        ("database_statement_timeout_seconds", 60.0),
        ("cache_timeout_seconds", 0.1),
        ("cache_timeout_seconds", 60.0),
        ("event_source_timeout_seconds", 60.0),
        ("event_live_import_interval_seconds", 60.0),
        ("event_full_import_interval_seconds", 86400.0),
        ("event_import_days", 30),
        ("access_token_seconds", 60),
        ("access_token_seconds", 86400),
        ("refresh_token_days", 90),
        ("login_max_failures", 1),
        ("login_lockout_seconds", 60),
        ("stream_audio_grace_seconds", 0),
        ("stream_audio_grace_seconds", 86400),
        ("hls_segment_seconds", 1),
        ("hls_segment_seconds", 10),
        ("livekit_api_timeout_seconds", 60.0),
        ("sync_reference_seconds", 30),
        ("sync_reference_seconds", 600),
        ("listener_window_seconds", 30),
        ("hsts_seconds", 63_072_000),
        ("max_request_bytes", 65_536),
    ],
    ids=[
        "connect-lower-bound",
        "connect-upper-bound",
        "statement-small",
        "statement-upper-bound",
        "cache-small",
        "cache-upper-bound",
        "event-source-upper-bound",
        "live-interval-minimum",
        "full-interval-a-day",
        "import-days-maximum",
        "access-token-minute",
        "access-token-day",
        "refresh-token-maximum",
        "lockout-after-one-failure",
        "lockout-minimum",
        "audio-grace-none",
        "audio-grace-a-day",
        "segment-shortest",
        "segment-longest",
        "livekit-api-upper-bound",
        "sync-reference-shortest",
        "sync-reference-longest",
        "listener-window-shortest",
        "hsts-two-years",
        "smallest-request-cap",
    ],
)
def test_accepts_timeouts_within_bounds(field: str, value: float) -> None:
    assert getattr(build_settings(**{field: value}), field) == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_connect_timeout_seconds", 1.9),
        ("database_connect_timeout_seconds", 60.1),
        ("database_statement_timeout_seconds", 0.0),
        ("database_statement_timeout_seconds", 60.1),
        ("cache_timeout_seconds", 0.0),
        ("cache_timeout_seconds", 60.1),
        ("event_source_timeout_seconds", 0.0),
        ("event_live_import_interval_seconds", 59.0),
        ("event_full_import_interval_seconds", 86401.0),
        ("event_import_days", 31),
        ("event_import_days", 0),
        ("access_token_seconds", 59),
        ("access_token_seconds", 86401),
        ("refresh_token_days", 0),
        ("refresh_token_days", 91),
        ("login_max_failures", 0),
        ("login_lockout_seconds", 59),
        ("stream_audio_grace_seconds", -1),
        ("stream_audio_grace_seconds", 86401),
        ("hls_segment_seconds", 0),
        ("hls_segment_seconds", 11),
        ("livekit_api_timeout_seconds", 0.0),
        ("sync_reference_seconds", 29),
        ("sync_reference_seconds", 601),
        ("listener_window_seconds", 29),
        ("hsts_seconds", -1),
        ("max_request_bytes", 65_535),
        ("max_request_bytes", 16 * 1024 * 1024 + 1),
    ],
    ids=[
        "connect-below-driver-minimum",
        "connect-too-long",
        "statement-zero",
        "statement-too-long",
        "cache-zero",
        "cache-too-long",
        "event-source-zero",
        "live-interval-too-frequent",
        "full-interval-over-a-day",
        "import-days-leaves-no-room-for-yesterday",
        "import-days-zero",
        "access-token-under-a-minute",
        "access-token-over-a-day",
        "refresh-token-zero",
        "refresh-token-too-long",
        "lockout-never",
        "lockout-too-short",
        "audio-grace-negative",
        "audio-grace-over-a-day",
        "segment-zero",
        "segment-too-long-to-sit-close-behind",
        "livekit-api-zero",
        "sync-reference-too-short-to-be-useful",
        "sync-reference-too-much-memory",
        "listener-window-shorter-than-check-ins",
        "hsts-negative",
        "request-cap-below-a-webhook",
        "request-cap-too-big",
    ],
)
def test_rejects_timeouts_out_of_bounds(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        build_settings(**{field: value})


def test_rejects_unknown_log_level(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("COMMENTARY_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_are_immutable() -> None:
    settings = build_settings()
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"


def test_cors_origins_are_read_as_json(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("COMMENTARY_CORS_ORIGINS", '["http://localhost:3000"]')
    assert Settings().cors_origins == ("http://localhost:3000",)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "origin",
    ["*", "http://localhost:3000/", "http://localhost:3000/studio", "localhost:3000", "ftp://x"],
    ids=["wildcard", "trailing-slash", "path", "no-scheme", "not-http"],
)
def test_cors_origins_must_be_exact_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        build_settings(cors_origins=(origin,))


def test_hls_is_off_by_default() -> None:
    settings = build_settings()
    assert (settings.records_hls, settings.livekit_api_url, settings.hls_base_url) == (
        False,
        None,
        None,
    )


def test_hls_is_on_with_both_urls(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("COMMENTARY_LIVEKIT_API_URL", "http://livekit:7880")
    environment.setenv("COMMENTARY_HLS_BASE_URL", "https://hls.example.com")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.records_hls
    assert str(settings.livekit_api_url) == "http://livekit:7880/"


@pytest.mark.parametrize(
    "half",
    [{"livekit_api_url": "http://livekit:7880"}, {"hls_base_url": "https://hls.example.com"}],
    ids=["api-url-only", "base-url-only"],
)
def test_hls_with_one_url_is_refused(half: dict[str, str]) -> None:
    """A recorder nobody can play, or playlists nothing records, is a mistake."""
    with pytest.raises(ValidationError, match="both livekit_api_url and hls_base_url"):
        build_settings(**half)


@pytest.mark.parametrize(
    "root",
    ["/hls", "hls", "/srv/hls/live", "recordings_2026"],
    ids=["absolute", "s3-prefix", "nested", "underscore"],
)
def test_accepts_hls_output_roots(root: str) -> None:
    assert build_settings(hls_output_root=root).hls_output_root == root


@pytest.mark.parametrize(
    "root",
    ["", "/", "/hls/", "../etc", "/hls/../etc", "/hls live"],
    ids=["empty", "root", "trailing-slash", "parent", "climbs-out", "space"],
)
def test_rejects_hls_output_roots_that_escape_or_break_paths(root: str) -> None:
    with pytest.raises(ValidationError):
        build_settings(hls_output_root=root)


def test_the_matcher_is_unset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMMENTARY_SYNC_MATCHER", raising=False)
    assert MatcherSettings().sync_matcher is None


@pytest.mark.parametrize(
    "name", ["", "Baseline", "../x", "a b"], ids=["empty", "capitals", "path", "space"]
)
def test_rejects_matcher_names_that_are_not_entry_point_names(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv("COMMENTARY_SYNC_MATCHER", name)
    with pytest.raises(ValidationError):
        MatcherSettings()
