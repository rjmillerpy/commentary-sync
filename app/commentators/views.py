"""HTTP endpoints for commentators.

POST  /commentators           the signed-in account becomes a commentator
GET   /commentators           one page of commentators, by handle
GET   /commentators/me        the signed-in account's commentator profile
PATCH /commentators/me        edit it
GET   /commentators/{handle}  one commentator
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.commentators import service
from app.commentators.errors import (
    AlreadyCommentatorError,
    CommentatorNotFoundError,
    HandleTakenError,
    NotACommentatorError,
)
from app.commentators.models import MAX_HANDLE_LENGTH, Commentator
from app.commentators.schema import (
    CommentatorPage,
    CommentatorResponse,
    CommentatorSignup,
    ProfileUpdate,
)
from app.common.db import get_db
from app.common.pagination import DEFAULT_PAGE_SIZE, PageLimit, PageOffset
from app.common.rate_limit import RateLimit, rate_limited
from app.common.schema import documented_errors

commentators_router = APIRouter(tags=["commentators"])

NOT_A_COMMENTATOR_DETAIL = "This account is not a commentator"
# Becoming a commentator and editing the profile: rare, so tight. It also
# slows anyone trying handles one after another.
PROFILE_CHANGES_PER_HOUR = RateLimit("commentator-change-hour", limit=20, window_seconds=60 * 60)
PROFILE_CHANGE_LIMIT = [Depends(rate_limited(PROFILE_CHANGES_PER_HOUR))]

Database = Annotated[AsyncSession, Depends(get_db)]
SignedIn = Annotated[User, Depends(current_user)]


@commentators_router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.CONFLICT, HTTPStatus.TOO_MANY_REQUESTS
    ),
    dependencies=PROFILE_CHANGE_LIMIT,
)
async def become_commentator(
    signup: CommentatorSignup, user: SignedIn, db: Database
) -> CommentatorResponse:
    try:
        commentator = await service.become_commentator(db, user, signup)
    except AlreadyCommentatorError as error:
        raise HTTPException(HTTPStatus.CONFLICT, "This account is already a commentator") from error
    except HandleTakenError as error:
        raise HTTPException(HTTPStatus.CONFLICT, "Handle already taken") from error
    return _to_response(commentator)


@commentators_router.get("")
async def list_commentators(
    db: Database, limit: PageLimit = DEFAULT_PAGE_SIZE, offset: PageOffset = 0
) -> CommentatorPage:
    commentators = await service.list_commentators(db, limit=limit, offset=offset)
    return CommentatorPage.build(
        [_to_response(commentator) for commentator in commentators], limit=limit, offset=offset
    )


# Declared before /{handle}, which would otherwise match "me". No handle is
# that short, so none is hidden by this route.
@commentators_router.get(
    "/me", responses=documented_errors(HTTPStatus.UNAUTHORIZED, HTTPStatus.NOT_FOUND)
)
async def my_profile(user: SignedIn, db: Database) -> CommentatorResponse:
    try:
        commentator = await service.get_own_profile(db, user.id)
    except NotACommentatorError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, NOT_A_COMMENTATOR_DETAIL) from error
    return _to_response(commentator)


@commentators_router.patch(
    "/me",
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED, HTTPStatus.NOT_FOUND, HTTPStatus.TOO_MANY_REQUESTS
    ),
    dependencies=PROFILE_CHANGE_LIMIT,
)
async def update_my_profile(
    update: ProfileUpdate, user: SignedIn, db: Database
) -> CommentatorResponse:
    try:
        commentator = await service.update_profile(db, user.id, update)
    except NotACommentatorError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, NOT_A_COMMENTATOR_DETAIL) from error
    return _to_response(commentator)


@commentators_router.get("/{handle}", responses=documented_errors(HTTPStatus.NOT_FOUND))
async def get_commentator(
    handle: Annotated[str, Path(max_length=MAX_HANDLE_LENGTH)], db: Database
) -> CommentatorResponse:
    try:
        commentator = await service.get_by_handle(db, handle)
    except CommentatorNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commentator not found") from error
    return _to_response(commentator)


def _to_response(commentator: Commentator) -> CommentatorResponse:
    return CommentatorResponse(
        id=commentator.id,
        handle=commentator.handle,
        display_name=commentator.user.display_name,
        bio=commentator.bio,
        created_at=commentator.created_at,
    )
