"""Per-client rate limits, counted in Redis.

    @router.post("/login", dependencies=[Depends(rate_limited(LOGIN))])

Each policy allows `limit` requests per client in a window that starts at the
client's first request and lasts `window_seconds`. Request number limit + 1
gets 429 with `Retry-After`.

A client is its IP address as the app sees it (`request.client`), not
X-Forwarded-For, which anyone can set. Behind a load balancer, uvicorn must
be told to trust it (`--forwarded-allow-ips`) so the address it reports is the
real client's. IPv6 clients are limited per /64 network, because one device
is usually given a whole /64 and could otherwise rotate through it. Keys hold
a hash of the address, not the address.
"""

import hashlib
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.common.cache import count_in_window, get_cache
from app.common.http_headers import RETRY_AFTER_HEADER

logger = logging.getLogger(__name__)

KEY_PREFIX = "rate-limit:"
IPV6_NETWORK_PREFIX = 64
UNKNOWN_CLIENT = "unknown"
RATE_LIMITED_DETAIL = "Too many requests; try again later"


@dataclass(frozen=True)
class RateLimit:
    """At most `limit` requests per client per `window_seconds`."""

    name: str
    limit: int
    window_seconds: int


def client_identity(request: Request) -> str:
    """The address a client is limited by: its IPv4 address, or its IPv6 /64."""
    host = request.client.host if request.client is not None else UNKNOWN_CLIENT
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host  # not an IP (a Unix socket, a test client): limit it as it is
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    if address.ipv4_mapped is not None:  # ::ffff:1.2.3.4 is the IPv4 client 1.2.3.4
        return str(address.ipv4_mapped)
    return str(ipaddress.ip_network(f"{address}/{IPV6_NETWORK_PREFIX}", strict=False))


def rate_limit_key(policy: RateLimit, client: str) -> str:
    return f"{KEY_PREFIX}{policy.name}:{hashlib.sha256(client.encode()).hexdigest()}"


def rate_limited(policy: RateLimit) -> Callable[[Request, Redis], Awaitable[None]]:
    """A FastAPI dependency that enforces `policy` on the route it guards."""

    async def enforce(request: Request, cache: Annotated[Redis, Depends(get_cache)]) -> None:
        key = rate_limit_key(policy, client_identity(request))
        try:
            count, remaining = await count_in_window(cache, key, policy.window_seconds)
        except RedisError:
            # Fail open: an outage shouldn't take every guarded route down with
            # it. Login stays protected by its account lockout, which fails closed.
            logger.warning("rate limit %s not enforced: Redis unavailable", policy.name)
            return
        if count > policy.limit:
            logger.warning("rate limit %s exceeded", policy.name)
            raise HTTPException(
                HTTPStatus.TOO_MANY_REQUESTS,
                RATE_LIMITED_DETAIL,
                headers={RETRY_AFTER_HEADER: str(max(remaining, 1))},
            )

    return enforce
