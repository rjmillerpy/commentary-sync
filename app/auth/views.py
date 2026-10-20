"""HTTP endpoints for accounts and sign-in.

POST /auth/register  create an account; returns a token pair
POST /auth/login     email and password for a token pair
POST /auth/refresh   a refresh token for a new pair (the old one stops working)
POST /auth/logout    end the session a refresh token belongs to
GET  /auth/me        the signed-in account
"""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service, sessions
from app.auth.dependencies import CHALLENGE, current_user
from app.auth.errors import (
    AuthUnavailableError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    LoginLockedError,
)
from app.auth.models import User
from app.auth.schema import Credentials, RefreshRequest, Registration, TokenPair, UserResponse
from app.common.cache import get_cache
from app.common.config import Settings, get_settings
from app.common.db import get_db
from app.common.http_headers import CACHE_CONTROL_HEADER, NO_STORE, RETRY_AFTER_HEADER
from app.common.rate_limit import RateLimit, rate_limited
from app.common.schema import documented_errors

auth_router = APIRouter(tags=["auth"])


# Per client IP. The account lockout stops guessing one account's password;
# these stop one client guessing across many accounts, or creating them in bulk.
LOGIN_PER_MINUTE = RateLimit("auth-login-minute", limit=10, window_seconds=60)
LOGIN_PER_HOUR = RateLimit("auth-login-hour", limit=100, window_seconds=60 * 60)
REGISTER_PER_HOUR = RateLimit("auth-register-hour", limit=5, window_seconds=60 * 60)
REFRESH_PER_MINUTE = RateLimit("auth-refresh-minute", limit=30, window_seconds=60)


@auth_router.post(
    "/register",
    status_code=HTTPStatus.CREATED,
    responses=documented_errors(HTTPStatus.CONFLICT, HTTPStatus.TOO_MANY_REQUESTS),
    dependencies=[Depends(rate_limited(REGISTER_PER_HOUR))],
)
async def register(
    registration: Registration,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    try:
        pair = await service.register(db, registration, settings, now=datetime.now(UTC))
    except EmailTakenError as error:
        raise HTTPException(HTTPStatus.CONFLICT, "Email already registered") from error
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # it carries tokens
    return pair


@auth_router.post(
    "/login",
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE
    ),
    dependencies=[Depends(rate_limited(LOGIN_PER_MINUTE)), Depends(rate_limited(LOGIN_PER_HOUR))],
)
async def login(
    credentials: Credentials,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[Redis, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    try:
        pair = await service.log_in(db, cache, credentials, settings, now=datetime.now(UTC))
    except InvalidCredentialsError as error:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Wrong email or password") from error
    except LoginLockedError as error:
        raise HTTPException(
            HTTPStatus.TOO_MANY_REQUESTS,
            "Too many wrong passwords; try again later",
            headers={RETRY_AFTER_HEADER: str(error.retry_after_seconds)},
        ) from error
    except AuthUnavailableError as error:
        # Fail closed: without the lockout count, passwords could be guessed without limit.
        raise HTTPException(
            HTTPStatus.SERVICE_UNAVAILABLE, "Sign-in is unavailable; try again shortly"
        ) from error
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # it carries tokens
    return pair


@auth_router.post(
    "/refresh",
    responses=documented_errors(HTTPStatus.UNAUTHORIZED, HTTPStatus.TOO_MANY_REQUESTS),
    dependencies=[Depends(rate_limited(REFRESH_PER_MINUTE))],
)
async def refresh(
    request: RefreshRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    try:
        pair = await sessions.rotate_session(
            db, request.refresh_token.get_secret_value(), settings, now=datetime.now(UTC)
        )
    except InvalidTokenError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, "Session expired; sign in again", headers=CHALLENGE
        ) from error
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # it carries tokens
    return pair


@auth_router.post("/logout", status_code=HTTPStatus.NO_CONTENT)
async def logout(request: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    await sessions.end_session(db, request.refresh_token.get_secret_value())


@auth_router.get("/me", responses=documented_errors(HTTPStatus.UNAUTHORIZED))
async def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)
