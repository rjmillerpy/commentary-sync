"""API contract, security and regression tests for /auth."""

import time

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.auth.lockout import failure_key
from app.auth.schema import TokenPair
from app.auth.views import LOGIN_PER_HOUR, LOGIN_PER_MINUTE, REFRESH_PER_MINUTE, REGISTER_PER_HOUR
from app.common.cache import get_cache
from app.common.rate_limit import RATE_LIMITED_DETAIL
from tests.conftest import DISPLAY_NAME, EMAIL, PASSWORD, Account, LogLines, bearer

WRONG_PASSWORD = "not the password at all"
MAX_FAILURES = 5  # the default in Settings
TOKEN_PAIR_FIELDS = {"access_token", "refresh_token", "token_type", "expires_in"}


def log_in(api: TestClient, password: str, email: str = EMAIL) -> httpx2.Response:
    return api.post("/auth/login", json={"email": email, "password": password})


def fail_logins(api: TestClient, times: int) -> None:
    for _ in range(times):
        assert log_in(api, WRONG_PASSWORD).status_code == 401


# Registration


def test_register_returns_a_token_pair_that_signs_in(api: TestClient) -> None:
    response = api.post(
        "/auth/register",
        json={"email": "New.Fan@Example.com", "password": PASSWORD, "display_name": "  New  "},
    )
    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == TOKEN_PAIR_FIELDS
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60

    me = api.get("/auth/me", headers=bearer(body["access_token"])).json()
    assert set(me) == {"id", "email", "display_name", "created_at"}
    assert me["email"] == "new.fan@example.com"  # stored in one case
    assert me["display_name"] == "New"


@pytest.mark.parametrize(
    "email", [EMAIL, EMAIL.upper(), f"  {EMAIL}  "], ids=["same", "other-case", "padded"]
)
def test_an_email_registers_once(api: TestClient, account: Account, email: str) -> None:
    response = api.post(
        "/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Again"}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"email": "a" * 250 + "@example.com"},
        {"password": "x" * 11},
        {"password": "x" * 257},
        {"display_name": ""},
        {"display_name": "   "},
        {"display_name": "x" * 51},
    ],
    ids=[
        "email-malformed",
        "email-too-long",
        "password-too-short",
        "password-too-long",
        "name-empty",
        "name-blank",
        "name-too-long",
    ],
)
def test_register_validates_its_input(api: TestClient, overrides: dict[str, object]) -> None:
    body = {"email": EMAIL, "password": PASSWORD, "display_name": DISPLAY_NAME, **overrides}
    assert api.post("/auth/register", json=body).status_code == 422


def test_register_ignores_fields_it_does_not_take(api: TestClient) -> None:
    """Mass assignment: a client can't set anything but the three fields."""
    body = {"email": EMAIL, "password": PASSWORD, "display_name": DISPLAY_NAME, "id": "x"}
    response = api.post("/auth/register", json={**body, "session_version": 99})
    assert response.status_code == 201
    me = api.get("/auth/me", headers=bearer(response.json()["access_token"])).json()
    assert me["id"] != "x"


def test_a_rejected_password_is_not_echoed_back(api: TestClient) -> None:
    """FastAPI's 422 body normally includes the input; a password must not be in it."""
    secret = "short-pass"
    response = api.post(
        "/auth/register",
        json={"email": EMAIL, "password": secret, "display_name": DISPLAY_NAME},
    )
    assert response.status_code == 422
    assert secret not in response.text


# Login


def test_login_with_the_right_password(api: TestClient, account: Account) -> None:
    response = log_in(api, PASSWORD, email=EMAIL.upper())
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    pair = TokenPair.model_validate(response.json())
    assert pair.refresh_token != account.tokens.refresh_token  # a new session
    assert api.get("/auth/me", headers=bearer(pair.access_token)).status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [(EMAIL, WRONG_PASSWORD), ("nobody@example.com", PASSWORD)],
    ids=["wrong-password", "unknown-email"],
)
def test_failed_logins_look_the_same(
    api: TestClient, account: Account, email: str, password: str
) -> None:
    """Neither the status nor the message says whether the account exists."""
    response = log_in(api, password, email=email)
    assert response.status_code == 401
    assert response.json() == {"detail": "Wrong email or password"}


def test_the_password_hash_never_leaves_the_server(api: TestClient, account: Account) -> None:
    me = api.get("/auth/me", headers=bearer(account.tokens.access_token))
    assert "argon2" not in me.text
    assert "password" not in me.text


# Lockout


def test_too_many_wrong_passwords_lock_the_account(api: TestClient, account: Account) -> None:
    fail_logins(api, MAX_FAILURES)
    response = log_in(api, PASSWORD)  # even the right password
    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 15 * 60
    assert response.json() == {"detail": "Too many wrong passwords; try again later"}


def test_one_failure_short_of_the_limit_still_signs_in(api: TestClient, account: Account) -> None:
    fail_logins(api, MAX_FAILURES - 1)
    assert log_in(api, PASSWORD).status_code == 200


def test_a_successful_login_resets_the_count(api: TestClient, account: Account) -> None:
    fail_logins(api, MAX_FAILURES - 1)
    assert log_in(api, PASSWORD).status_code == 200
    fail_logins(api, MAX_FAILURES - 1)
    assert log_in(api, PASSWORD).status_code == 200


def test_locking_one_account_leaves_others_alone(api: TestClient, account: Account) -> None:
    fail_logins(api, MAX_FAILURES)
    other = api.post(
        "/auth/register",
        json={"email": "other@example.com", "password": PASSWORD, "display_name": "Other"},
    )
    assert other.status_code == 201
    assert log_in(api, PASSWORD, email="other@example.com").status_code == 200


@pytest.mark.anyio
async def test_regression_the_lockout_ends_when_its_window_does(
    api: TestClient, account: Account, cache: Redis
) -> None:
    """Regression: a lockout must end by itself. Here Redis expires the count,
    as it would when the window runs out, and the account signs in again."""
    fail_logins(api, MAX_FAILURES)
    assert log_in(api, PASSWORD).status_code == 429

    await cache.pexpire(failure_key(EMAIL), 1)
    time.sleep(0.01)
    assert log_in(api, PASSWORD).status_code == 200


@pytest.mark.anyio
async def test_regression_every_failure_count_has_an_expiry(
    api: TestClient, account: Account, cache: Redis
) -> None:
    """Regression: a count written without an expiry would lock the account
    forever. Every count must carry one from its first failure."""
    fail_logins(api, 1)
    assert 0 < await cache.ttl(failure_key(EMAIL)) <= 15 * 60


@pytest.mark.anyio
async def test_regression_a_stale_count_without_an_expiry_is_given_one(
    api: TestClient, account: Account, cache: Redis
) -> None:
    """Regression: a stale count left with no expiry (an old deploy, a manual
    write) locks once more, then expires like any other."""
    await cache.set(failure_key(EMAIL), MAX_FAILURES)
    assert log_in(api, PASSWORD).status_code == 429
    assert 0 < await cache.ttl(failure_key(EMAIL)) <= 15 * 60


def test_login_fails_closed_when_redis_is_down(
    app: FastAPI, api: TestClient, account: Account, unreachable_cache: Redis
) -> None:
    """Without the lockout count, passwords could be guessed without limit."""
    app.dependency_overrides[get_cache] = lambda: unreachable_cache
    response = log_in(api, PASSWORD)
    assert response.status_code == 503
    assert response.json() == {"detail": "Sign-in is unavailable; try again shortly"}


# Refresh and logout


def refresh(api: TestClient, refresh_token: str) -> httpx2.Response:
    return api.post("/auth/refresh", json={"refresh_token": refresh_token})


def test_refresh_trades_the_token_for_a_new_pair(api: TestClient, account: Account) -> None:
    response = refresh(api, account.tokens.refresh_token)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    pair = TokenPair.model_validate(response.json())
    assert pair.refresh_token != account.tokens.refresh_token
    assert api.get("/auth/me", headers=bearer(pair.access_token)).status_code == 200
    assert refresh(api, pair.refresh_token).status_code == 200


def test_a_reused_refresh_token_ends_every_session(api: TestClient, account: Account) -> None:
    """Token theft: the old token comes back after it was spent. Neither the
    attacker's nor the real client's tokens keep working."""
    rotated = TokenPair.model_validate(refresh(api, account.tokens.refresh_token).json())
    other_device = TokenPair.model_validate(log_in(api, PASSWORD).json())

    reused = refresh(api, account.tokens.refresh_token)
    assert reused.status_code == 401
    assert reused.headers["WWW-Authenticate"] == "Bearer"
    assert reused.json() == {"detail": "Session expired; sign in again"}

    for pair in (rotated, other_device):
        assert refresh(api, pair.refresh_token).status_code == 401
        assert api.get("/auth/me", headers=bearer(pair.access_token)).status_code == 401
    assert log_in(api, PASSWORD).status_code == 200  # the password still works


@pytest.mark.parametrize("token", ["never-issued", "x" * 128], ids=["unknown", "longest-allowed"])
def test_an_unknown_refresh_token_is_rejected(
    api: TestClient, account: Account, token: str
) -> None:
    assert refresh(api, token).status_code == 401
    # Nothing was ended: an unknown token proves nothing about this account.
    assert refresh(api, account.tokens.refresh_token).status_code == 200


@pytest.mark.parametrize("token", ["", "x" * 129], ids=["empty", "too-long"])
def test_a_malformed_refresh_token_is_a_validation_error(api: TestClient, token: str) -> None:
    assert refresh(api, token).status_code == 422


def test_logout_ends_the_session(api: TestClient, account: Account) -> None:
    other_device = TokenPair.model_validate(log_in(api, PASSWORD).json())
    body = {"refresh_token": account.tokens.refresh_token}
    response = api.post("/auth/logout", json=body)
    assert response.status_code == 204
    assert response.content == b""
    assert refresh(api, account.tokens.refresh_token).status_code == 401
    assert refresh(api, other_device.refresh_token).status_code == 200  # only this device


def test_logout_twice_is_not_an_error(api: TestClient, account: Account) -> None:
    body = {"refresh_token": account.tokens.refresh_token}
    assert api.post("/auth/logout", json=body).status_code == 204
    assert api.post("/auth/logout", json=body).status_code == 204


# The signed-in account


def test_me_without_a_token_is_401(api: TestClient) -> None:
    response = api.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not signed in"}


def test_auth_routes_are_documented(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]
    assert {"/auth/register", "/auth/login", "/auth/refresh", "/auth/logout", "/auth/me"} <= set(
        paths
    )
    assert "429" in paths["/auth/login"]["post"]["responses"]


# Per-IP rate limits


def test_one_client_cant_guess_across_many_accounts(api: TestClient) -> None:
    """The lockout is per account; this is per client, whatever the email."""
    for index in range(LOGIN_PER_MINUTE.limit):
        assert log_in(api, WRONG_PASSWORD, email=f"user{index}@example.com").status_code == 401
    response = log_in(api, WRONG_PASSWORD, email="another@example.com")
    assert response.status_code == 429
    assert response.json() == {"detail": RATE_LIMITED_DETAIL}
    assert "Retry-After" in response.headers


def test_one_client_cant_register_in_bulk(api: TestClient) -> None:
    for index in range(REGISTER_PER_HOUR.limit):
        body = {"email": f"bulk{index}@example.com", "password": PASSWORD, "display_name": "B"}
        assert api.post("/auth/register", json=body).status_code == 201
    body = {"email": "one-more@example.com", "password": PASSWORD, "display_name": "B"}
    assert api.post("/auth/register", json=body).status_code == 429


def test_one_client_cant_hammer_refresh(api: TestClient) -> None:
    for _ in range(REFRESH_PER_MINUTE.limit):
        assert refresh(api, "never-issued").status_code == 401
    assert refresh(api, "never-issued").status_code == 429


def test_login_rate_limits_are_tighter_per_minute_than_per_hour() -> None:
    per_minute_rate = LOGIN_PER_MINUTE.limit / LOGIN_PER_MINUTE.window_seconds
    per_hour_rate = LOGIN_PER_HOUR.limit / LOGIN_PER_HOUR.window_seconds
    assert LOGIN_PER_MINUTE.limit < LOGIN_PER_HOUR.limit
    assert per_hour_rate < per_minute_rate  # the hourly cap bites on sustained guessing


def test_a_whole_sign_in_flow_logs_no_secrets_or_email(
    api: TestClient, log_lines: LogLines
) -> None:
    """Rule 18, on the JSON log as written: no email, password or token."""
    registered = api.post(
        "/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "display_name": DISPLAY_NAME},
    ).json()
    log_in(api, WRONG_PASSWORD)
    pair = log_in(api, PASSWORD).json()
    refreshed = refresh(api, pair["refresh_token"]).json()
    api.get("/auth/me", headers=bearer(refreshed["access_token"]))
    api.post("/auth/logout", json={"refresh_token": refreshed["refresh_token"]})

    written = str(log_lines())
    assert "account" in written  # the flow was logged
    secrets_used = [EMAIL, PASSWORD, WRONG_PASSWORD]
    for tokens in (registered, pair, refreshed):
        secrets_used += [tokens["access_token"], tokens["refresh_token"]]
    for secret in secrets_used:
        assert secret not in written
