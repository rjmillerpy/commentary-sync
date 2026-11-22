import time
import uuid

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.common.cache import get_cache
from app.events.models import Event
from app.streams import sync_health
from app.streams.health_views import HEALTH_READS_PER_MINUTE
from app.streams.schema import SyncResult, SyncStatus
from tests.conftest import Account, bearer, register_account
from tests.streams.conftest import go_live, make_commentator

pytestmark = pytest.mark.anyio


def health(api: TestClient, account: Account, stream_id: object) -> httpx2.Response:
    return api.get(f"/streams/{stream_id}/sync-health", headers=bearer(account.tokens.access_token))


async def test_the_commentator_sees_how_their_listeners_are_syncing(
    api: TestClient, account: Account, event: Event, cache: Redis
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    stream_id = uuid.UUID(str(stream["id"]))
    now = time.time()
    found = SyncResult(status=SyncStatus.MATCHED, delay_seconds=22.0, peak_ratio=3.0)
    await sync_health.record(cache, stream_id, uuid.uuid4(), found, now=now)
    await sync_health.record(
        cache, stream_id, uuid.uuid4(), SyncResult(status=SyncStatus.NOT_FOUND), now=now
    )
    response = health(api, account, stream_id)
    assert response.status_code == 200
    assert response.json() == {"in_sync": 1, "not_heard": 1, "typical_delay_seconds": 22.0}


async def test_with_nobody_synced_yet_it_says_so(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    assert health(api, account, stream["id"]).json() == {
        "in_sync": 0,
        "not_heard": 0,
        "typical_delay_seconds": None,
    }


async def test_only_the_commentator_sees_it(
    api: TestClient, account: Account, event: Event
) -> None:
    """Security: listeners' results are the commentator's business, nobody else's."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    other = register_account(api, "other@example.com", "Other")
    assert health(api, other, stream["id"]).status_code == 404
    assert api.get(f"/streams/{stream['id']}/sync-health").status_code == 401


async def test_an_ended_stream_has_none(api: TestClient, account: Account, event: Event) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    api.post(f"/streams/{stream['id']}/end", headers=bearer(account.tokens.access_token))
    assert health(api, account, stream["id"]).status_code == 409


async def test_with_redis_down_try_again_shortly(
    api: TestClient, app: FastAPI, account: Account, event: Event, unreachable_cache: Redis
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    app.dependency_overrides[get_cache] = lambda: unreachable_cache
    response = health(api, account, stream["id"])
    assert (response.status_code, response.json()) == (503, {"detail": "Try again shortly"})


async def test_reads_are_rate_limited(api: TestClient, account: Account) -> None:
    statuses = [
        health(api, account, uuid.uuid4()).status_code
        for _ in range(HEALTH_READS_PER_MINUTE.limit + 1)
    ]
    assert statuses[-1] == 429
