"""The rate-limit dependency on a route of its own, as a domain would use it."""

import logging
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from starlette.requests import Request

from app.common.cache import get_cache
from app.common.rate_limit import (
    RATE_LIMITED_DETAIL,
    RateLimit,
    client_identity,
    rate_limit_key,
    rate_limited,
)
from app.common.schema import FrozenModel

POLICY = RateLimit("test", limit=3, window_seconds=60)
CLIENT = ("203.0.113.7", 50000)


class GuardedResponse(FrozenModel):
    ok: bool


@pytest.fixture
def guarded_app(app: FastAPI) -> FastAPI:
    @app.get("/guarded", dependencies=[Depends(rate_limited(POLICY))])
    async def guarded() -> GuardedResponse:
        return GuardedResponse(ok=True)

    return app


def client_at(app: FastAPI, host: str) -> TestClient:
    return TestClient(app, client=(host, 50000))


@pytest.fixture
def api(guarded_app: FastAPI) -> Iterator[TestClient]:
    with client_at(guarded_app, CLIENT[0]) as client:
        yield client


def use_up(api: TestClient, policy: RateLimit = POLICY) -> None:
    for _ in range(policy.limit):
        assert api.get("/guarded").status_code == 200


def test_requests_up_to_the_limit_pass(api: TestClient) -> None:
    use_up(api)


def test_the_request_after_the_limit_is_429(api: TestClient) -> None:
    use_up(api)
    response = api.get("/guarded")
    assert response.status_code == 429
    assert response.json() == {"detail": RATE_LIMITED_DETAIL}
    assert 0 < int(response.headers["Retry-After"]) <= POLICY.window_seconds


@pytest.mark.anyio
async def test_the_limit_resets_when_the_window_ends(api: TestClient, cache: Redis) -> None:
    use_up(api)
    await cache.delete(rate_limit_key(POLICY, CLIENT[0]))  # the window's key expiring
    assert api.get("/guarded").status_code == 200


def test_other_clients_have_their_own_limit(api: TestClient, guarded_app: FastAPI) -> None:
    use_up(api)
    with client_at(guarded_app, "198.51.100.2") as other:
        assert other.get("/guarded").status_code == 200


def test_x_forwarded_for_does_not_buy_more_requests(api: TestClient) -> None:
    """Anyone can set the header, so it must not change who the client is."""
    for index in range(POLICY.limit):
        headers = {"X-Forwarded-For": f"192.0.2.{index}"}
        assert api.get("/guarded", headers=headers).status_code == 200
    assert api.get("/guarded", headers={"X-Forwarded-For": "192.0.2.99"}).status_code == 429


def test_one_ipv6_network_shares_a_limit(guarded_app: FastAPI) -> None:
    """A device given a /64 can't rotate addresses to escape the limit."""
    for suffix in range(POLICY.limit):
        with client_at(guarded_app, f"2001:db8:1:2::{suffix + 1}") as client:
            assert client.get("/guarded").status_code == 200
    with client_at(guarded_app, "2001:db8:1:2:ffff::9") as client:
        assert client.get("/guarded").status_code == 429
    with client_at(guarded_app, "2001:db8:1:3::1") as neighbour:  # the next /64
        assert neighbour.get("/guarded").status_code == 200


def test_policies_count_separately(guarded_app: FastAPI, api: TestClient) -> None:
    other_policy = RateLimit("other", limit=1, window_seconds=60)

    @guarded_app.get("/other", dependencies=[Depends(rate_limited(other_policy))])
    async def other() -> None:
        return None

    use_up(api)
    assert api.get("/other").status_code == 200


def test_redis_down_lets_requests_through_and_logs(
    guarded_app: FastAPI,
    api: TestClient,
    unreachable_cache: Redis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    guarded_app.dependency_overrides[get_cache] = lambda: unreachable_cache
    with caplog.at_level(logging.WARNING, logger="app.common.rate_limit"):
        for _ in range(POLICY.limit + 1):
            assert api.get("/guarded").status_code == 200
    assert "rate limit test not enforced: Redis unavailable" in caplog.text


@pytest.mark.anyio
async def test_redis_holds_no_ip_addresses(api: TestClient, cache: Redis) -> None:
    api.get("/guarded")
    [key] = await cache.keys("*")
    assert CLIENT[0] not in key


def request_from(host: str | None) -> Request:
    scope = {"type": "http", "client": (host, 1) if host is not None else None}
    return Request(scope)


@pytest.mark.parametrize(
    ("host", "identity"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("testclient", "testclient"),
        (None, "unknown"),
    ],
    ids=["ipv4", "ipv6-to-its-64", "ipv4-mapped-ipv6", "not-an-ip", "no-client"],
)
def test_client_identity(host: str | None, identity: str) -> None:
    assert client_identity(request_from(host)) == identity
