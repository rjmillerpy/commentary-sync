"""Shared fixtures: a synthetic broadcast, real audio files, and the API with its clients."""

import io
import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import fakeredis
import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, WebsocketUrl
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.auth.schema import TokenPair
from app.common.cache import get_cache
from app.common.config import Settings
from app.common.db import create_database_engine, get_db
from app.common.logs import configure_logging
from app.main import create_app
from app.simulation.broadcast import SOURCE_SAMPLE_RATE, synthesise_broadcast
from app.simulation.service import to_analysis_rate
from app.sync.audio import encode_aac
from app.sync.schema import Samples

BROADCAST_SECONDS = 40.0
FILE_BIT_RATE = 64_000

# Nothing listens on port 1, so connecting fails at once with a real driver error.
CLOSED_PORT_CACHE_URL = "redis://127.0.0.1:1/0"
UNREACHABLE_TIMEOUT_SECONDS = 2.0
TEST_AUTH_SECRET = "test-only-auth-secret-at-least-32-chars"
TEST_LIVEKIT_URL = "ws://127.0.0.1:7880"
TEST_LIVEKIT_API_KEY = "test-livekit-key"
TEST_LIVEKIT_API_SECRET = "test-only-livekit-secret-at-least-32-chars"
# Every required setting that isn't a database or cache URL, as environment variables.
REQUIRED_ENVIRONMENT = {
    "COMMENTARY_AUTH_SECRET": TEST_AUTH_SECRET,
    "COMMENTARY_LIVEKIT_URL": TEST_LIVEKIT_URL,
    "COMMENTARY_LIVEKIT_API_KEY": TEST_LIVEKIT_API_KEY,
    "COMMENTARY_LIVEKIT_API_SECRET": TEST_LIVEKIT_API_SECRET,
}

EMAIL = "fan@example.com"
PASSWORD = "correct horse battery staple"
DISPLAY_NAME = "Fan"

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

AudioWriter = Callable[[str, Samples], Path]
LogLines = Callable[[], list[dict[str, object]]]


@dataclass(frozen=True)
class Account:
    email: str
    password: str
    tokens: TokenPair


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def register_account(
    api: TestClient, email: str = EMAIL, display_name: str = DISPLAY_NAME
) -> Account:
    """An account registered through the API, the way a real client makes one."""
    response = api.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": display_name},
    )
    assert response.status_code == 201, response.text
    return Account(email, PASSWORD, TokenPair.model_validate(response.json()))


def export_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the URLs in the environment, where Alembic's env.py reads them."""
    monkeypatch.setenv("COMMENTARY_DATABASE_URL", settings.database_url.get_secret_value())
    monkeypatch.setenv("COMMENTARY_CACHE_URL", settings.cache_url.get_secret_value())
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="session", autouse=True)
def baseline_matcher() -> Iterator[None]:
    """Every test runs the public baseline matcher (app/sync/baseline.py),
    whatever else is installed, unless it picks another itself."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("COMMENTARY_SYNC_MATCHER", "baseline")
        yield


@pytest.fixture(scope="session")
def broadcast() -> Samples:
    """A 40 s synthetic broadcast at the source sample rate."""
    return synthesise_broadcast(np.random.default_rng(11), BROADCAST_SECONDS)


@pytest.fixture(scope="session")
def other_broadcast() -> Samples:
    """A different broadcast, which must never match `broadcast`."""
    return synthesise_broadcast(np.random.default_rng(12), BROADCAST_SECONDS)


@pytest.fixture(scope="session")
def analysis_broadcast(broadcast: Samples) -> Samples:
    return to_analysis_rate(broadcast)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(5)


@pytest.fixture
def write_audio(tmp_path: Path) -> AudioWriter:
    """Write source-rate samples to an .m4a file under tmp_path."""

    def write(name: str, samples: Samples) -> Path:
        path = tmp_path / name
        encode_aac(samples, SOURCE_SAMPLE_RATE, path, bit_rate=FILE_BIT_RATE)
        return path

    return write


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings for a real SQLite file. Redis is replaced in `app`, never dialled."""
    return Settings(
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"),
        cache_url=SecretStr(CLOSED_PORT_CACHE_URL),
        auth_secret=SecretStr(TEST_AUTH_SECRET),
        livekit_url=WebsocketUrl(TEST_LIVEKIT_URL),
        livekit_api_key=TEST_LIVEKIT_API_KEY,
        livekit_api_secret=SecretStr(TEST_LIVEKIT_API_SECRET),
    )


@pytest.fixture
def migrated_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """The same settings after `alembic upgrade head` has built the schema.

    Tables come from the migrations, never from the models, so a test that
    needs a table also proves a migration creates it.
    """
    export_settings(settings, monkeypatch)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    return settings


@pytest.fixture
async def db(migrated_settings: Settings) -> AsyncIterator[AsyncSession]:
    """A session on a database whose tables were built by the migrations."""
    engine = create_database_engine(migrated_settings)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def cache() -> Redis:
    """An in-memory Redis: the network is the one boundary the tests replace."""
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def app(settings: Settings, cache: Redis) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_cache] = lambda: cache
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Runs startup and shutdown. Server errors come back as responses, as in production."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    """Async tests (marked `anyio`) run on asyncio, the loop the app uses."""
    return "asyncio"


@pytest.fixture
def unreachable_engine(tmp_path: Path) -> AsyncEngine:
    """A real engine whose database can't be opened, so every query raises a
    genuine driver error (sqlite: "unable to open database file")."""
    return create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'no-such-directory' / 'app.db'}")


@pytest.fixture
def unreachable_cache() -> Redis:
    """A real Redis client pointed at a closed port: every command fails to connect."""
    return Redis.from_url(
        CLOSED_PORT_CACHE_URL,
        socket_connect_timeout=UNREACHABLE_TIMEOUT_SECONDS,
        socket_timeout=UNREACHABLE_TIMEOUT_SECONDS,
    )


@pytest.fixture
def client_with_outage(
    app: FastAPI, client: TestClient, unreachable_engine: AsyncEngine, unreachable_cache: Redis
) -> TestClient:
    """The app with both of its dependencies down."""

    async def unreachable_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(unreachable_engine) as session:
            yield session

    app.dependency_overrides[get_db] = unreachable_db
    app.dependency_overrides[get_cache] = lambda: unreachable_cache
    return client


@pytest.fixture
def log_lines(app: FastAPI) -> LogLines:
    """What the app writes to its log, as parsed JSON lines, from DEBUG up.

    Requests `app` first: building the app configures logging, and this
    replaces that handler with one writing to a buffer.
    """
    buffer = io.StringIO()
    configure_logging("DEBUG", "json", buffer)

    def read() -> list[dict[str, object]]:
        return [json.loads(line) for line in buffer.getvalue().splitlines()]

    return read


@pytest.fixture
def api(migrated_settings: Settings, app: FastAPI) -> Iterator[TestClient]:
    """The app on a database the migrations built; Redis is in memory."""
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def account(api: TestClient) -> Account:
    """An account registered through the API."""
    return register_account(api)
