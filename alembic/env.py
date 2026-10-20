"""Alembic environment: run migrations with the app's own settings and models."""

import asyncio

from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection, text

from app.common.config import Settings
from app.common.db import POSTGRES_BACKEND, create_migration_engine
from app.common.logs import configure_logging
from app.common.models import Base, import_all_models

# Any constant works; every migration run asks Postgres for the same lock.
MIGRATION_LOCK_ID = 726_627_901
TAKE_MIGRATION_LOCK = text("SELECT pg_advisory_xact_lock(:lock_id)")

import_all_models()
target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite can't ALTER most things; batch mode rebuilds the table instead.
        render_as_batch=True,
    )
    with context.begin_transaction():
        # Several containers can start at once. The lock lets one migrate while
        # the rest wait, then find the schema already current. It is released
        # when the transaction ends.
        if connection.dialect.name == POSTGRES_BACKEND:
            connection.execute(TAKE_MIGRATION_LOCK, {"lock_id": MIGRATION_LOCK_ID})
        context.run_migrations()


async def run_online() -> None:
    # pydantic-settings fills the required fields from the environment, which mypy can't see.
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)  # so each applied revision is logged
    engine = create_migration_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise CommandError("offline (--sql) mode is not supported; run against a database")
asyncio.run(run_online())
