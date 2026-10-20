"""`current_user`: the FastAPI dependency any endpoint uses to require sign-in.

@router.get("/mine")
async def mine(user: Annotated[User, Depends(current_user)]) -> ...
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.errors import InvalidTokenError
from app.auth.models import User
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
