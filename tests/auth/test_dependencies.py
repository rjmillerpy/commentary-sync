"""`current_user` on a route of its own, as another domain would use it."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import Listener, current_listener, current_user
from app.auth.models import User
from app.auth.schema import UserResponse
from tests.conftest import EMAIL, Account, LogLines, bearer, guest_token


@pytest.fixture
def protected(app: FastAPI, api: TestClient) -> TestClient:
    @app.get("/protected")
    async def protected_route(user: Annotated[User, Depends(current_user)]) -> UserResponse:
        return UserResponse.model_validate(user, from_attributes=True)

    return api


def test_a_signed_in_request_gets_its_account(protected: TestClient, account: Account) -> None:
    response = protected.get("/protected", headers=bearer(account.tokens.access_token))
    assert response.status_code == 200
    assert UserResponse.model_validate(response.json()).email == EMAIL


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "not-a-scheme"},
    ],
    ids=["no-header", "garbage-token", "empty-token", "basic-auth", "no-scheme"],
)
def test_anything_else_is_the_same_401(
    protected: TestClient, account: Account, headers: dict[str, str]
) -> None:
    response = protected.get("/protected", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not signed in"}


def test_a_refresh_token_is_not_an_access_token(protected: TestClient, account: Account) -> None:
    response = protected.get("/protected", headers=bearer(account.tokens.refresh_token))
    assert response.status_code == 401


def test_a_signed_in_request_names_its_account_in_the_log(
    protected: TestClient, account: Account, log_lines: LogLines
) -> None:
    """Rule 41: errors and access lines carry user context, by ID only."""
    me = protected.get("/auth/me", headers=bearer(account.tokens.access_token)).json()
    [access] = [line for line in log_lines() if line["message"] == "GET /auth/me 200"]
    assert access["account_id"] == me["id"]


@pytest.fixture
def listening(app: FastAPI, api: TestClient) -> TestClient:
    @app.get("/listening-only")
    async def listening_route(
        listener: Annotated[Listener, Depends(current_listener)],
    ) -> dict[str, object]:
        return {"id": str(listener.id), "is_guest": listener.is_guest}

    return api


def test_a_guest_is_a_listener(listening: TestClient) -> None:
    response = listening.get("/listening-only", headers=bearer(guest_token(listening)))
    assert response.status_code == 200
    assert response.json()["is_guest"] is True


def test_an_account_is_a_listener_too(listening: TestClient, account: Account) -> None:
    me = listening.get("/auth/me", headers=bearer(account.tokens.access_token)).json()
    response = listening.get("/listening-only", headers=bearer(account.tokens.access_token))
    assert response.json() == {"id": me["id"], "is_guest": False}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-token"}],
    ids=["no-header", "garbage-token"],
)
def test_anyone_else_is_not_a_listener(listening: TestClient, headers: dict[str, str]) -> None:
    response = listening.get("/listening-only", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
