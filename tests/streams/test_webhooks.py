import uuid

import pytest
from fastapi.testclient import TestClient

from app.events.models import Event
from app.streams.webhooks import MAX_WEBHOOK_BYTES
from tests.conftest import Account
from tests.streams.conftest import go_live, make_commentator, notice_body, sign_webhook, webhook

pytestmark = pytest.mark.anyio


async def test_livekit_closing_the_room_ends_the_stream(
    api: TestClient, account: Account, event: Event
) -> None:
    make_commentator(api, account)
    stream = go_live(api, account, event)
    body = notice_body("room_finished", uuid.UUID(str(stream["id"])))
    response = webhook(api, body, sign_webhook(body))
    assert (response.status_code, response.content) == (204, b"")
    assert api.get(f"/streams/{stream['id']}").json()["status"] == "ended"


async def test_notices_this_api_doesnt_act_on_are_acknowledged(api: TestClient) -> None:
    """Anything but 2xx makes LiveKit retry, so unknown rooms and events are a 204."""
    body = notice_body("track_published", uuid.uuid4(), "listener-1/PA_x")
    assert webhook(api, body, sign_webhook(body)).status_code == 204


@pytest.mark.parametrize(
    "authorization",
    [None, "not-a-jwt", sign_webhook(b"some other body")],
    ids=["unsigned", "garbage", "another-bodys-signature"],
)
async def test_a_webhook_livekit_didnt_sign_is_refused(
    api: TestClient, account: Account, event: Event, authorization: str | None
) -> None:
    """Security: nobody else can end a stream by posting a fake notice."""
    make_commentator(api, account)
    stream = go_live(api, account, event)
    response = webhook(
        api, notice_body("room_finished", uuid.UUID(str(stream["id"]))), authorization
    )
    assert (response.status_code, response.json()) == (
        401,
        {"detail": "Invalid webhook signature"},
    )
    assert api.get(f"/streams/{stream['id']}").json()["status"] == "live"


async def test_a_signed_webhook_that_isnt_a_notice_is_a_400(api: TestClient) -> None:
    body = b'{"room": {"name": "stream-x"}}'
    response = webhook(api, body, sign_webhook(body))
    assert (response.status_code, response.json()) == (400, {"detail": "Unreadable webhook"})


async def test_an_oversized_webhook_is_refused_before_it_is_checked(api: TestClient) -> None:
    body = b"x" * (MAX_WEBHOOK_BYTES + 1)
    response = webhook(api, body, sign_webhook(body))
    assert (response.status_code, response.json()) == (413, {"detail": "Request body too large"})
