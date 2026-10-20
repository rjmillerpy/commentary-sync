"""Settings read from the environment: the only place configuration enters the app."""

from typing import Annotated, Literal, Self

from fastapi import Request
from pydantic import Field, HttpUrl, SecretStr, WebsocketUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.common.logs import LogFormat

ENVIRONMENT_PREFIX = "COMMENTARY_"

# psycopg rejects connection timeouts under 2 s.
MIN_DATABASE_CONNECT_TIMEOUT_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 60.0
SECONDS_PER_DAY = 24 * 60 * 60
MIN_POLL_SECONDS = 60.0  # ESPN updates scores about once a minute; faster only adds load
MAX_IMPORT_DAYS = 31
# HS256 keys shorter than the 32-byte hash output are weaker than the algorithm.
MIN_AUTH_SECRET_LENGTH = 32
MAX_REFRESH_TOKEN_DAYS = 90
MAX_LOGIN_FAILURES = 100
# LiveKit signs room tokens with HS256 too.
MIN_LIVEKIT_SECRET_LENGTH = 32
# A scheme, a host and an optional port, as a browser sends it in `Origin`:
# no path, no trailing slash, no wildcard.
CorsOrigin = Annotated[str, Field(pattern=r"^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$")]
MAX_HLS_SEGMENT_SECONDS = 10
MIN_SYNC_REFERENCE_SECONDS = 30
MIN_LISTENER_WINDOW_SECONDS = 30
MAX_HSTS_SECONDS = 2 * 365 * SECONDS_PER_DAY
MIN_REQUEST_BYTES = 64 * 1024  # LiveKit's webhooks are up to this
MAX_REQUEST_BYTES = 16 * 1024 * 1024  # shorter than the app's check-ins would drop people
MAX_SYNC_REFERENCE_SECONDS = 600  # 10 minutes: about 13 MB of Redis per live stream


class Settings(BaseSettings):
    """Every value comes from a COMMENTARY_* variable, for example
    COMMENTARY_DATABASE_URL. The URLs are secrets because they carry passwords."""

    model_config = SettingsConfigDict(env_prefix=ENVIRONMENT_PREFIX, frozen=True)

    database_url: SecretStr
    cache_url: SecretStr
    # Signs access tokens. Generate one with
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    auth_secret: SecretStr = Field(min_length=MIN_AUTH_SECRET_LENGTH)
    database_connect_timeout_seconds: float = Field(
        default=5.0, ge=MIN_DATABASE_CONNECT_TIMEOUT_SECONDS, le=MAX_TIMEOUT_SECONDS
    )
    database_statement_timeout_seconds: float = Field(default=10.0, gt=0, le=MAX_TIMEOUT_SECONDS)
    cache_timeout_seconds: float = Field(default=2.0, gt=0, le=MAX_TIMEOUT_SECONDS)
    event_source_timeout_seconds: float = Field(default=10.0, gt=0, le=MAX_TIMEOUT_SECONDS)
    # The scheduler: re-import the coming days every `full` seconds, and while
    # a league has games on, today's games every `live` seconds.
    event_full_import_interval_seconds: float = Field(
        default=6 * 60 * 60, ge=MIN_POLL_SECONDS, le=SECONDS_PER_DAY
    )
    event_live_import_interval_seconds: float = Field(
        default=5 * 60, ge=MIN_POLL_SECONDS, le=SECONDS_PER_DAY
    )
    # One day fewer than the import limit: the scheduler also re-reads yesterday.
    event_import_days: int = Field(default=7, ge=1, le=MAX_IMPORT_DAYS - 1)
    # Auth: access tokens are short-lived because they are checked without a
    # session lookup; refresh tokens are long-lived and revocable.
    access_token_seconds: int = Field(default=15 * 60, ge=60, le=SECONDS_PER_DAY)
    refresh_token_days: int = Field(default=30, ge=1, le=MAX_REFRESH_TOKEN_DAYS)
    # After this many wrong passwords for one account, logins to it are refused
    # until `login_lockout_seconds` after the first of them.
    login_max_failures: int = Field(default=5, ge=1, le=MAX_LOGIN_FAILURES)
    login_lockout_seconds: int = Field(default=15 * 60, ge=60, le=SECONDS_PER_DAY)
    # LiveKit, the media server that carries commentary audio. The URL is the
    # one clients connect to (ws:// locally, wss:// deployed); the API never
    # calls it, it only signs the tokens clients join rooms with.
    livekit_url: WebsocketUrl
    livekit_api_key: str = Field(min_length=1)
    livekit_api_secret: SecretStr = Field(min_length=MIN_LIVEKIT_SECRET_LENGTH)
    # A room token only has to last until the client joins; LiveKit keeps a
    # joined client connected after it expires.
    livekit_token_seconds: int = Field(default=10 * 60, ge=60, le=SECONDS_PER_DAY)
    # A stream whose commentator's audio has been gone this long is ended by
    # the scheduler. Long enough to ride out a reload or a network switch.
    stream_audio_grace_seconds: int = Field(default=2 * 60, ge=0, le=SECONDS_PER_DAY)
    # HLS for listeners whose TV is far behind (app/streams/recorder.py). Off
    # unless both URLs are set: `livekit_api_url` is where this API calls
    # LiveKit's server API (internal: http://livekit:7880 in compose), and
    # `hls_base_url` is where listeners fetch the recordings (the `hls` service
    # locally, CloudFront deployed). LiveKit Egress writes them under
    # `hls_output_root`: a directory locally, a key prefix with S3 upload.
    livekit_api_url: HttpUrl | None = None
    hls_base_url: HttpUrl | None = None
    hls_output_root: str = Field(default="/hls", pattern=r"^/?[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$")
    hls_segment_seconds: int = Field(default=2, ge=1, le=MAX_HLS_SEGMENT_SECONDS)
    livekit_api_timeout_seconds: float = Field(default=5.0, gt=0, le=MAX_TIMEOUT_SECONDS)
    # A listener counts as listening for this long after their app last
    # checked in (it checks in every 20 s, so this rides out two misses).
    listener_window_seconds: int = Field(
        default=60, ge=MIN_LISTENER_WINDOW_SECONDS, le=SECONDS_PER_DAY
    )
    # Sync: how much of each commentator's room audio is kept to match
    # listeners' TV recordings against (app/streams/reference.py). It bounds
    # how far apart two TVs can be and still sync: streaming services run up
    # to a minute or two behind cable.
    sync_reference_seconds: int = Field(
        default=240, ge=MIN_SYNC_REFERENCE_SECONDS, le=MAX_SYNC_REFERENCE_SECONDS
    )
    # Browser origins allowed to call the API, as JSON:
    #   COMMENTARY_CORS_ORIGINS='["http://localhost:3000"]'
    # Empty (the default) allows none. Exact origins only, never "*".
    cors_origins: tuple[CorsOrigin, ...] = ()
    # Production hardening (app/common/security_headers.py, body_limit.py).
    # The interactive docs are on locally; a deployed API turns them off.
    api_docs: bool = True
    # Sent as Strict-Transport-Security once served over HTTPS; 0 sends none.
    hsts_seconds: int = Field(default=0, ge=0, le=MAX_HSTS_SECONDS)
    # No request body may be larger: above the largest audio upload (1 MB).
    max_request_bytes: int = Field(
        default=2 * 1024 * 1024, ge=MIN_REQUEST_BYTES, le=MAX_REQUEST_BYTES
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # json: one object per line, for CloudWatch or Loki. console: readable text.
    log_format: LogFormat = "json"

    @model_validator(mode="after")
    def _hls_needs_both_urls(self) -> Self:
        if (self.livekit_api_url is None) != (self.hls_base_url is None):
            raise ValueError("HLS needs both livekit_api_url and hls_base_url, or neither")
        return self

    @property
    def records_hls(self) -> bool:
        return self.hls_base_url is not None


class MatcherSettings(BaseSettings):
    """Which sync matcher to use (app/sync/matcher.py), from COMMENTARY_SYNC_MATCHER.

    Apart from Settings because the command-line tools need it without a
    database or a cache. Unset, the matcher module picks one.
    """

    model_config = SettingsConfigDict(env_prefix=ENVIRONMENT_PREFIX, frozen=True)

    sync_matcher: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")


def get_settings(request: Request) -> Settings:
    """FastAPI dependency: the settings the app was built with."""
    settings: Settings = request.app.state.settings
    return settings
