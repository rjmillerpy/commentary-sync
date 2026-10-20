"""`current_user` on a route of its own, as another domain would use it."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import current_user
from app.auth.models import User
from app.auth.schema import UserResponse
from tests.conftest import EMAIL, Account, LogLines, bearer


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
