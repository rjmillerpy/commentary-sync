import logging

import pytest
from argon2 import PasswordHasher

from app.auth import passwords

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery staple"


async def test_a_hash_verifies_its_own_password_only() -> None:
    stored = await passwords.hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert await passwords.verify_password(stored, PASSWORD)
    assert not await passwords.verify_password(stored, PASSWORD + "!")


async def test_the_same_password_hashes_differently_each_time() -> None:
    """Each hash has its own salt, so equal passwords don't show as equal hashes."""
    assert await passwords.hash_password(PASSWORD) != await passwords.hash_password(PASSWORD)


async def test_the_unknown_account_hash_matches_no_ordinary_password() -> None:
    assert passwords.UNKNOWN_ACCOUNT_HASH.startswith("$argon2id$")
    assert not await passwords.verify_password(passwords.UNKNOWN_ACCOUNT_HASH, PASSWORD)


async def test_a_corrupt_stored_hash_fails_and_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="app.auth.passwords"):
        assert not await passwords.verify_password("not-a-hash", PASSWORD)
    assert "not a valid Argon2 hash" in caplog.text
    assert PASSWORD not in caplog.text


@pytest.mark.parametrize(
    ("hasher", "expected"),
    [(PasswordHasher(), False), (PasswordHasher(time_cost=1, memory_cost=8 * 1024), True)],
    ids=["current-settings", "weaker-settings"],
)
def test_hashes_made_with_older_settings_need_redoing(
    hasher: PasswordHasher, expected: bool
) -> None:
    assert passwords.needs_rehash(hasher.hash(PASSWORD)) is expected
