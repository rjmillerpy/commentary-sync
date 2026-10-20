"""Password hashing with Argon2id, off the event loop."""

import logging

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

logger = logging.getLogger(__name__)

# argon2-cffi's defaults are RFC 9106's low-memory profile: 64 MiB and about
# 50 ms per hash. That is CPU and memory work, so it runs in a worker thread,
# and at most this many at once: 40 parallel logins would otherwise need 2.5 GB.
MAX_CONCURRENT_HASHES = 4

_hasher = PasswordHasher()
_hash_slots = anyio.CapacityLimiter(MAX_CONCURRENT_HASHES)

# Checked when no account has the email, so an unknown email takes as long to
# reject as a wrong password and response times don't reveal who has an account.
UNKNOWN_ACCOUNT_HASH = _hasher.hash("no account has this password")


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher.hash, password, limiter=_hash_slots)


async def verify_password(password_hash: str, password: str) -> bool:
    return await anyio.to_thread.run_sync(_check, password_hash, password, limiter=_hash_slots)


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with older settings and should be redone."""
    return _hasher.check_needs_rehash(password_hash)


def _check(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except InvalidHashError:
        # A stored hash argon2 can't parse is a data problem, not a wrong password.
        logger.error("stored password hash is not a valid Argon2 hash")
        return False
    except VerificationError:
        # A wrong password: argon2 reports a mismatch only by raising. Not
        # logged here; the caller logs the failed login.
        return False
