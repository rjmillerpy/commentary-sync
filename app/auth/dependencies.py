"""`current_user`: the FastAPI dependency any endpoint uses to require sign-in.

@router.get("/mine")
async def mine(user: Annotated[User, Depends(current_user)]) -> ...

`current_listener`: for the listening routes, which guests may use too: an
account's access token or a guest token (POST /auth/guest).
"""

import uuid
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.errors import InvalidTokenError
from app.auth.models import User
from app.auth.tokens import read_guest_token
from app.common.config import Settings, get_settings
from app.common.db import get_db
from app.common.request_tracing import bind_account

NOT_SIGNED_IN_DETAIL = "Not signed in"
# RFC 6750: a 401 for a bearer-protected resource says which scheme it wants.
CHALLENGE = {"WWW-Authenticate": "Bearer"}

# auto_error off: a missing header gets the same 401 as a bad token, instead
# of FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, NOT_SIGNED_IN_DETAIL, headers=CHALLENGE)
    try:
        user = await service.authenticate(db, credentials.credentials, settings)
    except InvalidTokenError as error:
        raise HTTPException(
            HTTPStatus.UNAUTHORIZED, NOT_SIGNED_IN_DETAIL, headers=CHALLENGE
        ) from error
    bind_account(user.id)
    return user


@dataclass(frozen=True)
class Listener:
    """Someone listening: an account, or a guest."""

    id: uuid.UUID
    is_guest: bool


async def current_listener(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Listener:
    if credentials is None:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, NOT_SIGNED_IN_DETAIL, headers=CHALLENGE)
    try:
        guest = read_guest_token(
            credentials.credentials, secret=settings.auth_secret.get_secret_value()
        )
    except InvalidTokenError:
        user = await current_user(credentials, db, settings)  # not a guest: an account, or a 401
        return Listener(id=user.id, is_guest=False)
    bind_account(guest)
    return Listener(id=guest, is_guest=True)
