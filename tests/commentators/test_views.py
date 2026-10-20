import pytest
from fastapi.testclient import TestClient

from app.commentators.models import MAX_HANDLE_LENGTH
from app.commentators.views import PROFILE_CHANGES_PER_HOUR
from tests.conftest import DISPLAY_NAME, EMAIL, Account, bearer, register_account

Json = dict[str, object]

RESPONSE_FIELDS = {"id", "handle", "display_name", "bio", "created_at"}


def sign_up(api: TestClient, account: Account, handle: str = "fan_cast", bio: str = "") -> Json:
    response = api.post(
        "/commentators",
        json={"handle": handle, "bio": bio},
        headers=bearer(account.tokens.access_token),
    )
    assert response.status_code == 201, response.text
    profile: Json = response.json()
    return profile


def test_becoming_a_commentator_returns_the_public_profile(
    api: TestClient, account: Account
) -> None:
    profile = sign_up(api, account, handle="Fan_Cast", bio="Bears, every snap.")
    assert set(profile) == RESPONSE_FIELDS
    assert profile["handle"] == "fan_cast"
    assert profile["display_name"] == DISPLAY_NAME
    assert profile["bio"] == "Bears, every snap."


def test_becoming_a_commentator_needs_sign_in(api: TestClient) -> None:
    response = api.post("/commentators", json={"handle": "fan_cast"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_an_account_becomes_a_commentator_once(api: TestClient, account: Account) -> None:
    sign_up(api, account)
    response = api.post(
        "/commentators",
        json={"handle": "second_try"},
        headers=bearer(account.tokens.access_token),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "This account is already a commentator"}


def test_a_handle_is_taken_in_any_case(api: TestClient, account: Account) -> None:
    sign_up(api, account, handle="fan_cast")
    other = register_account(api, "other@example.com", "Other")
    response = api.post(
        "/commentators", json={"handle": "FAN_CAST"}, headers=bearer(other.tokens.access_token)
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Handle already taken"}


@pytest.mark.parametrize(
    "body",
    [{}, {"handle": "no spaces"}, {"handle": "me"}, {"handle": "ok_handle", "bio": "x" * 501}],
    ids=["no-handle", "bad-characters", "me-is-too-short", "bio-too-long"],
)
def test_sign_up_validates_its_input(api: TestClient, account: Account, body: Json) -> None:
    response = api.post("/commentators", json=body, headers=bearer(account.tokens.access_token))
    assert response.status_code == 422


def test_own_profile(api: TestClient, account: Account) -> None:
    created = sign_up(api, account)
    response = api.get("/commentators/me", headers=bearer(account.tokens.access_token))
    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize(
    ("method", "body"), [("GET", None), ("PATCH", {"bio": "x"})], ids=["get", "patch"]
)
def test_own_profile_of_a_listener_is_404(
    api: TestClient, account: Account, method: str, body: Json | None
) -> None:
    response = api.request(
        method, "/commentators/me", json=body, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "This account is not a commentator"}


@pytest.mark.parametrize(
    ("method", "body"), [("GET", None), ("PATCH", {"bio": "x"})], ids=["get", "patch"]
)
def test_own_profile_needs_sign_in(api: TestClient, method: str, body: Json | None) -> None:
    assert api.request(method, "/commentators/me", json=body).status_code == 401


def test_editing_the_bio(api: TestClient, account: Account) -> None:
    sign_up(api, account, bio="Old bio.")
    response = api.patch(
        "/commentators/me",
        json={"bio": "  New bio.  "},
        headers=bearer(account.tokens.access_token),
    )
    assert response.status_code == 200
    assert response.json()["bio"] == "New bio."
    assert api.get("/commentators/fan_cast").json()["bio"] == "New bio."


def test_the_handle_cant_be_edited(api: TestClient, account: Account) -> None:
    """A link to a commentator never starts pointing at someone else."""
    sign_up(api, account)
    response = api.patch(
        "/commentators/me",
        json={"bio": "x", "handle": "new_handle"},
        headers=bearer(account.tokens.access_token),
    )
    assert response.json()["handle"] == "fan_cast"


@pytest.mark.parametrize("handle", ["fan_cast", "FAN_CAST"], ids=["exact", "upper-case"])
def test_anyone_can_look_up_a_commentator(api: TestClient, account: Account, handle: str) -> None:
    created = sign_up(api, account)
    response = api.get(f"/commentators/{handle}")
    assert response.status_code == 200
    assert response.json() == created


def test_unknown_handle_is_404(api: TestClient) -> None:
    response = api.get("/commentators/nobody")
    assert response.status_code == 404
    assert response.json() == {"detail": "Commentator not found"}


def test_an_over_long_handle_is_refused_before_any_query(api: TestClient) -> None:
    assert api.get(f"/commentators/{'a' * (MAX_HANDLE_LENGTH + 1)}").status_code == 422


def test_anyone_can_list_commentators_by_handle(api: TestClient, account: Account) -> None:
    sign_up(api, account, handle="zulu")
    other = register_account(api, "other@example.com", "Other")
    sign_up(api, other, handle="alpha")
    first = api.get("/commentators", params={"limit": 1}).json()
    second = api.get("/commentators", params={"limit": 1, "offset": 1}).json()
    third = api.get("/commentators", params={"limit": 1, "offset": 2}).json()
    assert ([item["handle"] for item in first["items"]], first["next_offset"]) == (["alpha"], 1)
    assert ([item["handle"] for item in second["items"]], second["next_offset"]) == (["zulu"], 2)
    assert (third["items"], third["next_offset"]) == ([], None)


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10_001}],
    ids=["limit-zero", "limit-over-100", "offset-negative", "offset-too-deep"],
)
def test_list_rejects_bad_paging(api: TestClient, params: dict[str, int]) -> None:
    """Rules 5 and 11: input is validated at the boundary and pages are bounded."""
    assert api.get("/commentators", params=params).status_code == 422


def test_no_commentator_response_shows_the_account_email(api: TestClient, account: Account) -> None:
    """The profile is public: the email belongs to the account, not the profile."""
    sign_up(api, account)
    responses = [
        api.get("/commentators/me", headers=bearer(account.tokens.access_token)),
        api.get("/commentators/fan_cast"),
        api.get("/commentators"),
    ]
    assert all(EMAIL not in response.text for response in responses)


@pytest.mark.parametrize(
    ("path", "method", "status", "model"),
    [
        ("/commentators", "post", "201", "CommentatorResponse"),
        ("/commentators", "post", "409", "ErrorDetail"),
        ("/commentators", "get", "200", "CommentatorPage"),
        ("/commentators/me", "get", "200", "CommentatorResponse"),
        ("/commentators/me", "patch", "404", "ErrorDetail"),
        ("/commentators/{handle}", "get", "200", "CommentatorResponse"),
        ("/commentators/{handle}", "get", "404", "ErrorDetail"),
    ],
    ids=["signup-201", "signup-409", "list-200", "me-200", "patch-404", "get-200", "get-404"],
)
def test_documented_with_a_response_schema(
    api: TestClient, path: str, method: str, status: str, model: str
) -> None:
    """Rule 46: the OpenAPI schema names a model, not a free-form object."""
    documented = api.get("/openapi.json").json()["paths"][path][method]["responses"][status]
    assert documented["content"]["application/json"]["schema"]["$ref"].endswith(f"/{model}")


def test_profile_changes_are_rate_limited_per_client(api: TestClient, account: Account) -> None:
    """Also slows anyone trying handles one after another."""
    statuses = [
        api.patch(
            "/commentators/me", json={"bio": "x"}, headers=bearer(account.tokens.access_token)
        ).status_code
        for _ in range(PROFILE_CHANGES_PER_HOUR.limit)
    ]
    assert set(statuses) == {404}  # not a commentator yet
    response = api.post(
        "/commentators", json={"handle": "fan_cast"}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 429
