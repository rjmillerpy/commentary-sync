import time
import uuid

import httpx2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import get_cache
from app.common.config import Settings, get_settings
from app.events.models import Event
from app.events.schema import EventStatus
from app.streams import reference, tv_sync
from app.streams.recorder import Recorder, get_recorder
from app.streams.views import (
    CHECK_INS_PER_MINUTE,
    ROOM_TOKENS_PER_MINUTE,
    STREAM_CHANGES_PER_MINUTE,
    SYNCS_PER_MINUTE,
)
from app.sync.schema import Samples
from app.sync.service import extract_features
from tests.conftest import EMAIL, Account, bearer, register_account
from tests.streams.conftest import (
    START,
    STOP,
    TEST_HLS_BASE_URL,
    FakeEgress,
    add_event,
    go_live,
    make_commentator,
    notice_body,
    sign_webhook,
    webhook,
)

pytestmark = pytest.mark.anyio

Json = dict[str, object]
RESPONSE_FIELDS = {"id", "event_id", "commentator", "status", "started_at", "ended_at", "listeners"}


def end(api: TestClient, account: Account, stream_id: object) -> httpx2.Response:
    return api.post(f"/streams/{stream_id}/end", headers=bearer(account.tokens.access_token))


async def test_a_commentator_goes_live(api: TestClient, account: Account, event: Event) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    assert set(stream) == RESPONSE_FIELDS
    assert stream["event_id"] == str(event.id)
    assert stream["commentator"] == {"handle": "fan_cast", "display_name": "Fan"}
    assert (stream["status"], stream["ended_at"]) == ("live", None)


async def test_going_live_needs_sign_in(api: TestClient, event: Event) -> None:
    response = api.post("/streams", json={"event_id": str(event.id)})
    assert response.status_code == 401


async def test_a_listener_cant_go_live(api: TestClient, account: Account, event: Event) -> None:
    response = api.post(
        "/streams", json={"event_id": str(event.id)}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Only commentators can go live"}


async def test_going_live_on_an_unknown_event_is_404(api: TestClient, account: Account) -> None:
    make_commentator(api, account)
    response = api.post(
        "/streams",
        json={"event_id": str(uuid.uuid4())},
        headers=bearer(account.tokens.access_token),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


async def test_going_live_on_a_finished_event_is_409(
    api: TestClient, account: Account, db: AsyncSession
) -> None:
    finished = await add_event(db, EventStatus.FINAL)
    make_commentator(api, account)
    response = api.post(
        "/streams", json={"event_id": str(finished.id)}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "This event is over"}


async def test_going_live_twice_is_409(api: TestClient, account: Account, event: Event) -> None:
    make_commentator(api, account)
    go_live(api, account, event)
    response = api.post(
        "/streams", json={"event_id": str(event.id)}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "You are already live; end that stream first"}


async def test_ending_a_stream(api: TestClient, account: Account, event: Event) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    response = end(api, account, stream["id"])
    assert response.status_code == 200
    ended = response.json()
    assert ended["status"] == "ended"
    assert ended["ended_at"] is not None
    assert api.get(f"/streams/{stream['id']}").json()["status"] == "ended"


async def test_ending_twice_is_409(api: TestClient, account: Account, event: Event) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    end(api, account, stream["id"])
    response = end(api, account, stream["id"])
    assert response.status_code == 409
    assert response.json() == {"detail": "This stream has already ended"}


async def test_someone_elses_stream_looks_missing(
    api: TestClient, account: Account, event: Event
) -> None:
    """Security: ending another commentator's stream gets the same 404 as a
    stream that doesn't exist, and the stream stays live."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    intruder = register_account(api, "intruder@example.com", "Intruder")
    make_commentator(api, intruder, "intruder")
    response = end(api, intruder, stream["id"])
    assert (response.status_code, response.json()) == (404, {"detail": "Stream not found"})
    assert end(api, intruder, uuid.uuid4()).json() == response.json()
    assert api.get(f"/streams/{stream['id']}").json()["status"] == "live"


async def test_ending_needs_sign_in(api: TestClient) -> None:
    assert api.post(f"/streams/{uuid.uuid4()}/end").status_code == 401


async def test_unknown_stream_is_404(api: TestClient) -> None:
    response = api.get(f"/streams/{uuid.uuid4()}")
    assert (response.status_code, response.json()) == (404, {"detail": "Stream not found"})


async def test_anyone_can_list_live_streams_for_an_event(
    api: TestClient, account: Account, event: Event, db: AsyncSession
) -> None:
    other_event = await add_event(db, source_id="402")
    make_commentator(api, account, "alpha")
    go_live(api, account, event)
    other = register_account(api, "other@example.com", "Other")
    make_commentator(api, other, "bravo")
    go_live(api, other, other_event)

    page = api.get("/streams", params={"event_id": str(event.id)}).json()
    everything = api.get("/streams").json()
    assert [item["commentator"]["handle"] for item in page["items"]] == ["alpha"]
    assert page["next_offset"] is None
    assert len(everything["items"]) == 2


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"event_id": "nope"}],
    ids=["limit-zero", "limit-over-100", "offset-negative", "bad-event-id"],
)
async def test_list_rejects_bad_query_parameters(
    api: TestClient, params: dict[str, str | int]
) -> None:
    assert api.get("/streams", params=params).status_code == 422


async def test_no_stream_response_shows_an_email(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    responses = [api.get("/streams"), api.get(f"/streams/{stream['id']}")]
    assert all(EMAIL not in response.text for response in responses)


@pytest.mark.parametrize(
    ("path", "method", "status", "model"),
    [
        ("/streams", "post", "201", "StreamResponse"),
        ("/streams", "post", "403", "ErrorDetail"),
        ("/streams", "post", "409", "ErrorDetail"),
        ("/streams", "get", "200", "StreamPage"),
        ("/streams/{stream_id}/end", "post", "200", "StreamResponse"),
        ("/streams/{stream_id}/end", "post", "404", "ErrorDetail"),
        ("/streams/{stream_id}", "get", "200", "StreamResponse"),
        ("/streams/{stream_id}", "get", "404", "ErrorDetail"),
        ("/streams/{stream_id}/publisher-token", "post", "200", "RoomAccess"),
        ("/streams/{stream_id}/listener-token", "post", "200", "RoomAccess"),
        ("/streams/{stream_id}/listener-token", "post", "429", "ErrorDetail"),
        ("/streams/{stream_id}/listener-playlist", "post", "200", "PlaylistAccess"),
        ("/streams/{stream_id}/listener-playlist", "post", "409", "ErrorDetail"),
        ("/streams/{stream_id}/sync", "post", "200", "SyncResult"),
        ("/streams/{stream_id}/sync", "post", "400", "ErrorDetail"),
        ("/streams/{stream_id}/reference", "post", "400", "ErrorDetail"),
    ],
    ids=[
        "live-201",
        "live-403",
        "live-409",
        "list-200",
        "end-200",
        "end-404",
        "get-200",
        "get-404",
        "publisher-token-200",
        "listener-token-200",
        "listener-token-429",
        "playlist-200",
        "playlist-409",
        "sync-200",
        "sync-400",
        "reference-400",
    ],
)
async def test_documented_with_a_response_schema(
    api: TestClient, path: str, method: str, status: str, model: str
) -> None:
    """Rule 46: the OpenAPI schema names a model, not a free-form object."""
    documented = api.get("/openapi.json").json()["paths"][path][method]["responses"][status]
    assert documented["content"]["application/json"]["schema"]["$ref"].endswith(f"/{model}")


def token(api: TestClient, account: Account, stream_id: object, role: str) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/{role}-token", headers=bearer(account.tokens.access_token)
    )


async def test_the_commentator_and_a_listener_get_room_tokens(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    listener = register_account(api, "listener@example.com", "Listener")
    publisher = token(api, account, stream["id"], "publisher")
    heard = token(api, listener, stream["id"], "listener")
    for response in (publisher, heard):
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert set(response.json()) == {"url", "room", "token", "expires_in"}
        assert response.json()["room"] == f"stream-{stream['id']}"


async def test_a_listener_cant_get_the_publisher_token(
    api: TestClient, account: Account, event: Event
) -> None:
    """Security: only the stream's own commentator may send audio to its room."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    listener = register_account(api, "listener@example.com", "Listener")
    response = token(api, listener, stream["id"], "publisher")
    assert (response.status_code, response.json()) == (404, {"detail": "Stream not found"})


@pytest.mark.parametrize("role", ["publisher", "listener"], ids=["publisher", "listener"])
async def test_room_tokens_need_sign_in(api: TestClient, role: str) -> None:
    assert api.post(f"/streams/{uuid.uuid4()}/{role}-token").status_code == 401


@pytest.mark.parametrize("role", ["publisher", "listener"], ids=["publisher", "listener"])
async def test_an_ended_stream_has_no_room(
    api: TestClient, account: Account, event: Event, role: str
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    end(api, account, stream["id"])
    response = token(api, account, stream["id"], role)
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "This stream has already ended"},
    )


async def test_room_tokens_are_rate_limited_per_client(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    statuses = [
        token(api, account, stream["id"], "listener").status_code
        for _ in range(ROOM_TOKENS_PER_MINUTE.limit + 1)
    ]
    assert statuses[:-1] == [200] * ROOM_TOKENS_PER_MINUTE.limit
    assert statuses[-1] == 429


async def test_live_streams_can_be_listed_for_one_commentator(
    api: TestClient, account: Account, event: Event
) -> None:
    """The studio finds the stream it was sending to before a reload."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    other = register_account(api, "other@example.com", "Other")
    make_commentator(api, other, "other_cast")
    go_live(api, other, event)
    page = api.get("/streams", params={"commentator": "FAN_CAST"}).json()
    assert [item["id"] for item in page["items"]] == [stream["id"]]
    end(api, account, stream["id"])
    assert api.get("/streams", params={"commentator": "fan_cast"}).json()["items"] == []


async def test_the_commentator_filter_is_bounded(api: TestClient) -> None:
    assert api.get("/streams", params={"commentator": "x" * 31}).status_code == 422


@pytest.fixture
def hls_api(
    api: TestClient, app: FastAPI, hls_settings: Settings, recorder: Recorder
) -> TestClient:
    """The API with HLS on, its recorder talking to FakeEgress."""
    app.dependency_overrides[get_settings] = lambda: hls_settings
    app.dependency_overrides[get_recorder] = lambda: recorder
    return api


def commentator_connects(api: TestClient, stream: Json, account: Account) -> None:
    """What LiveKit sends when the studio joins the stream's room."""
    me = api.get("/commentators/me", headers=bearer(account.tokens.access_token)).json()
    identity = f"commentator-{me['id']}/PA_one"
    body = notice_body("participant_joined", uuid.UUID(str(stream["id"])), identity)
    assert webhook(api, body, sign_webhook(body)).status_code == 204


def playlist(api: TestClient, account: Account, stream_id: object) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/listener-playlist", headers=bearer(account.tokens.access_token)
    )


async def test_a_listener_gets_the_playlist_once_the_commentator_connects(
    hls_api: TestClient, account: Account, event: Event, fake_egress: FakeEgress
) -> None:
    make_commentator(hls_api, account)
    stream = go_live(hls_api, account, event)
    listener = register_account(hls_api, "listener@example.com", "Listener")
    before = playlist(hls_api, listener, stream["id"])
    assert (before.status_code, before.json()) == (
        409,
        {"detail": "This stream has no HLS audio yet"},
    )
    commentator_connects(hls_api, stream, account)
    response = playlist(hls_api, listener, stream["id"])
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"  # the URL is the key
    url = response.json()["url"]
    assert url.startswith(f"{TEST_HLS_BASE_URL}/")
    assert url.endswith("/index.m3u8")
    assert len(fake_egress.calls(START)) == 1


async def test_ending_the_stream_stops_the_recording_and_the_playlist(
    hls_api: TestClient, account: Account, event: Event, fake_egress: FakeEgress
) -> None:
    make_commentator(hls_api, account)
    stream = go_live(hls_api, account, event)
    commentator_connects(hls_api, stream, account)
    assert end(hls_api, account, stream["id"]).status_code == 200
    assert fake_egress.calls(STOP) == [{"egress_id": "EG_test1"}]
    response = playlist(hls_api, account, stream["id"])
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "This stream has already ended"},
    )


async def test_the_playlist_needs_sign_in(hls_api: TestClient) -> None:
    """Security: the URL is the only key to the recording, so it goes only to accounts."""
    assert hls_api.post(f"/streams/{uuid.uuid4()}/listener-playlist").status_code == 401


async def test_an_unknown_stream_has_no_playlist(hls_api: TestClient, account: Account) -> None:
    response = playlist(hls_api, account, uuid.uuid4())
    assert (response.status_code, response.json()) == (404, {"detail": "Stream not found"})


async def test_with_hls_off_there_is_never_a_playlist(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    commentator_connects(api, stream, account)
    assert playlist(api, account, stream["id"]).status_code == 409


async def test_playlists_share_the_room_token_rate_limit(
    hls_api: TestClient, account: Account
) -> None:
    statuses = [
        playlist(hls_api, account, uuid.uuid4()).status_code
        for _ in range(ROOM_TOKENS_PER_MINUTE.limit + 1)
    ]
    assert statuses[-1] == 429


def send_reference(
    api: TestClient, account: Account, stream_id: object, pcm: bytes, at: float
) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/reference",
        params={"captured_at": at},
        content=pcm,
        headers={**bearer(account.tokens.access_token), "Content-Type": "application/octet-stream"},
    )


def send_features(
    api: TestClient, account: Account, stream_id: object, features: bytes, at: float
) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/sync",
        params={"captured_at": at},
        content=features,
        headers={**bearer(account.tokens.access_token), "Content-Type": "application/octet-stream"},
    )


async def test_the_studio_sends_room_audio_and_a_listener_syncs_to_it(
    api: TestClient,
    account: Account,
    event: Event,
    analysis_broadcast: Samples,
) -> None:
    """The whole path over HTTP: reference chunks in, features of the TV in, the delay out."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    start = time.time() - 50
    pcm = np.clip(analysis_broadcast * 32767, -32768, 32767).astype("<i2")
    for second in range(0, 40, 10):
        chunk = pcm[second * 8000 : (second + 10) * 8000].tobytes()
        assert send_reference(api, account, stream["id"], chunk, start + second).status_code == 204
    listener = register_account(api, "listener@example.com", "Listener")
    heard = extract_features(analysis_broadcast[12 * 8000 : 22 * 8000]).astype("<f4").tobytes()
    response = send_features(api, listener, stream["id"], heard, start + 12 + 6)
    assert response.status_code == 200
    assert response.json()["status"] == "matched"
    assert response.json()["delay_seconds"] == pytest.approx(6, abs=0.1)


async def test_sync_needs_sign_in(api: TestClient) -> None:
    response = api.post(
        f"/streams/{uuid.uuid4()}/sync", params={"captured_at": time.time()}, content=b"x"
    )
    assert response.status_code == 401


async def test_only_the_commentator_sends_their_reference(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    listener = register_account(api, "listener@example.com", "Listener")
    response = send_reference(api, listener, stream["id"], b"\x00\x00", time.time())
    assert (response.status_code, response.json()) == (404, {"detail": "Stream not found"})


@pytest.mark.parametrize(
    ("body", "seconds_ago", "detail"),
    [
        (b"not features", 0, "features come in frames of 16 float32 values"),
        (b"x" * 10, 3600, "capture time is 3600 s from the server's clock"),
    ],
    ids=["unreadable", "stale"],
)
async def test_unusable_recordings_are_a_400_that_says_why(
    api: TestClient, account: Account, event: Event, body: bytes, seconds_ago: float, detail: str
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    response = send_features(api, account, stream["id"], body, time.time() - seconds_ago)
    assert response.status_code == 400
    assert response.json()["detail"].startswith(detail)


async def test_oversized_audio_is_refused_unread(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    response = send_reference(
        api, account, stream["id"], b"\x00" * (reference.MAX_CHUNK_BYTES + 2), time.time()
    )
    assert response.status_code == 413


async def test_syncs_are_rate_limited_per_client(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    statuses = [
        send_features(api, account, stream["id"], b"x", time.time()).status_code
        for _ in range(SYNCS_PER_MINUTE.limit + 1)
    ]
    assert statuses[-1] == 429


def check_in(api: TestClient, account: Account, stream_id: object) -> httpx2.Response:
    return api.post(f"/streams/{stream_id}/listening", headers=bearer(account.tokens.access_token))


async def test_listeners_who_check_in_are_counted_on_the_stream(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    assert stream["listeners"] == 0
    for number in range(2):
        listener = register_account(api, f"listener{number}@example.com", "Listener")
        assert check_in(api, listener, stream["id"]).status_code == 204
        assert check_in(api, listener, stream["id"]).status_code == 204  # again: still one
    assert api.get(f"/streams/{stream['id']}").json()["listeners"] == 2
    assert (
        api.get("/streams", params={"event_id": str(event.id)}).json()["items"][0]["listeners"] == 2
    )


async def test_an_ended_stream_has_no_listeners_and_takes_no_check_ins(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    check_in(api, account, stream["id"])
    ended = end(api, account, stream["id"]).json()
    assert ended["listeners"] == 0
    assert api.get(f"/streams/{stream['id']}").json()["listeners"] == 0
    response = check_in(api, account, stream["id"])
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "This stream has already ended"},
    )


async def test_checking_in_needs_sign_in_and_a_real_stream(
    api: TestClient, account: Account
) -> None:
    assert api.post(f"/streams/{uuid.uuid4()}/listening").status_code == 401
    assert check_in(api, account, uuid.uuid4()).status_code == 404


async def test_with_redis_down_streams_still_list_with_unknown_counts(
    api: TestClient, app: FastAPI, account: Account, event: Event, unreachable_cache: Redis
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    app.dependency_overrides[get_cache] = lambda: unreachable_cache
    listing = api.get("/streams")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["listeners"] is None
    response = check_in(api, account, stream["id"])
    assert (response.status_code, response.json()) == (503, {"detail": "Try again shortly"})


async def test_check_ins_are_rate_limited_per_client(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    statuses = [
        check_in(api, account, stream["id"]).status_code
        for _ in range(CHECK_INS_PER_MINUTE.limit + 1)
    ]
    assert statuses[-1] == 429


async def test_going_live_and_ending_are_rate_limited_per_client(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    statuses = [
        end(api, account, uuid.uuid4()).status_code for _ in range(STREAM_CHANGES_PER_MINUTE.limit)
    ]
    assert set(statuses) == {404}
    response = api.post(
        "/streams", json={"event_id": str(event.id)}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 429  # the same budget


async def test_features_larger_than_20_seconds_are_refused_unread(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    oversized = b"\x00" * (tv_sync.MAX_FEATURE_BYTES + 64)
    assert send_features(api, account, stream["id"], oversized, time.time()).status_code == 413
