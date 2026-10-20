"""The migrations, run for real against a database file (cross-cutting, like test_structure)."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import make_url

from app.common.config import Settings
from tests.conftest import ALEMBIC_INI, export_settings

ALEMBIC_BOOKKEEPING_TABLE = "alembic_version"


@pytest.fixture
def alembic_config(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Config:
    export_settings(settings, monkeypatch)
    return Config(str(ALEMBIC_INI))


def table_names(settings: Settings) -> set[str]:
    database_file = make_url(settings.database_url.get_secret_value()).database
    assert database_file is not None
    if not Path(database_file).exists():
        return set()
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {name for (name,) in rows}


def test_upgrade_creates_the_schema(alembic_config: Config, settings: Settings) -> None:
    command.upgrade(alembic_config, "head")
    assert {"events", "users", "refresh_tokens", "commentators", "streams"} <= table_names(settings)


@pytest.mark.parametrize("target", ["0001", "base"], ids=["one-step", "all-the-way"])
def test_every_step_downgrades_and_upgrades_again(
    alembic_config: Config, settings: Settings, target: str
) -> None:
    """Each revision's downgrade undoes its upgrade, so a bad deploy can be rolled back."""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, target)
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


def test_models_and_migrations_agree(alembic_config: Config) -> None:
    """Fails when a model changed and nobody wrote the migration (`alembic check`)."""
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


def test_downgrade_removes_everything_upgrade_created(
    alembic_config: Config, settings: Settings
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    assert table_names(settings) <= {ALEMBIC_BOOKKEEPING_TABLE}


def test_upgrade_is_repeatable(alembic_config: Config, settings: Settings) -> None:
    """Every container start runs it, so a second run must be a no-op."""
    command.upgrade(alembic_config, "head")
    tables_after_first_run = table_names(settings)
    command.upgrade(alembic_config, "head")
    assert table_names(settings) == tables_after_first_run


def test_history_has_one_head() -> None:
    """Two heads means two branches were merged without a merge migration."""
    assert len(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()) == 1


def test_offline_mode_is_refused(alembic_config: Config) -> None:
    with pytest.raises(CommandError, match="offline"):
        command.upgrade(alembic_config, "head", sql=True)
