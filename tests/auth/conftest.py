"""Auth fixtures. The `api` and `account` fixtures are in tests/conftest.py,
shared with every domain that needs a signed-in user."""

from datetime import UTC, datetime

NOW = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
