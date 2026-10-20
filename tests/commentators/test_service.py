import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.commentators import service
from app.commentators.errors import (
    AlreadyCommentatorError,
    CommentatorNotFoundError,
    HandleTakenError,
    NotACommentatorError,
)
from app.commentators.models import Commentator
from app.commentators.schema import CommentatorSignup, ProfileUpdate

pytestmark = pytest.mark.anyio


async def new_user(db: AsyncSession, email: str = "fan@example.com", name: str = "Fan") -> User:
    user = User(email=email, display_name=name, password_hash="$argon2id$stand-in")
    db.add(user)
    await db.commit()
    return user


async def become(db: AsyncSession, user: User, handle: str = "fan_cast") -> Commentator:
    return await service.become_commentator(db, user, CommentatorSignup(handle=handle))


async def commentator_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Commentator))).scalar_one()


@pytest.mark.parametrize(
    ("given", "stored"),
    [("fan_cast", "fan_cast"), ("  Fan_Cast ", "fan_cast")],
    ids=["already-normal", "mixed-case-and-padding"],
)
def test_handles_are_normalised(given: str, stored: str) -> None:
    assert service.normalise_handle(given) == stored


async def test_becoming_a_commentator_links_the_profile_to_the_account(db: AsyncSession) -> None:
    user = await new_user(db)
    commentator = await service.become_commentator(
        db, user, CommentatorSignup(handle="Fan_Cast", bio="Bears, every snap.")
    )
    assert (commentator.user_id, commentator.handle) == (user.id, "fan_cast")
    assert commentator.bio == "Bears, every snap."
    assert commentator.user.display_name == "Fan"
    assert commentator.created_at is not None


async def test_an_account_becomes_a_commentator_once(db: AsyncSession) -> None:
    """A second profile is refused by the unique index on the account, and
    reported as that, even though its own handle is free."""
    user = await new_user(db)
    await become(db, user)
    with pytest.raises(AlreadyCommentatorError):
        await become(db, user, handle="another_handle")
    assert await commentator_count(db) == 1


async def test_a_taken_handle_is_refused_and_nothing_is_saved(db: AsyncSession) -> None:
    await become(db, await new_user(db))
    other = await new_user(db, "other@example.com")
    with pytest.raises(HandleTakenError):
        await become(db, other)
    assert await commentator_count(db) == 1


async def test_becoming_a_commentator_is_logged_by_id_only(
    db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    user = await new_user(db)
    with caplog.at_level(logging.INFO, logger=service.__name__):
        commentator = await become(db, user)
    assert str(user.id) in caplog.text
    assert str(commentator.id) in caplog.text
    assert "fan@example.com" not in caplog.text


async def test_own_profile(db: AsyncSession) -> None:
    user = await new_user(db)
    created = await become(db, user)
    assert (await service.get_own_profile(db, user.id)).id == created.id


async def test_own_profile_of_a_listener_is_an_error(db: AsyncSession) -> None:
    user = await new_user(db)
    with pytest.raises(NotACommentatorError):
        await service.get_own_profile(db, user.id)


async def test_update_changes_the_bio(db: AsyncSession) -> None:
    user = await new_user(db)
    await become(db, user)
    await service.update_profile(db, user.id, ProfileUpdate(bio="Now with stats."))
    db.expunge_all()
    assert (await service.get_own_profile(db, user.id)).bio == "Now with stats."


async def test_update_of_a_listener_is_an_error(db: AsyncSession) -> None:
    user = await new_user(db)
    with pytest.raises(NotACommentatorError):
        await service.update_profile(db, user.id, ProfileUpdate(bio="x"))


@pytest.mark.parametrize("handle", ["fan_cast", "FAN_CAST", " fan_cast "], ids=str.strip)
async def test_find_by_handle_in_any_case(db: AsyncSession, handle: str) -> None:
    created = await become(db, await new_user(db))
    assert (await service.get_by_handle(db, handle)).id == created.id


async def test_unknown_handle_is_an_error(db: AsyncSession) -> None:
    with pytest.raises(CommentatorNotFoundError):
        await service.get_by_handle(db, "nobody")


async def test_list_is_in_handle_order_and_paged(db: AsyncSession) -> None:
    for index, handle in enumerate(["charlie", "alpha", "bravo"]):
        await become(db, await new_user(db, f"fan{index}@example.com"), handle=handle)
    first = await service.list_commentators(db, limit=2, offset=0)
    rest = await service.list_commentators(db, limit=2, offset=2)
    assert [c.handle for c in first] == ["alpha", "bravo"]
    assert [c.handle for c in rest] == ["charlie"]


async def test_list_loads_every_account_in_one_query(db: AsyncSession) -> None:
    """Rule 21: no N+1. lazy="raise" makes a missing join fail here."""
    for index in range(3):
        await become(
            db, await new_user(db, f"fan{index}@example.com", f"Fan {index}"), f"fan{index}"
        )
    db.expunge_all()
    listed = await service.list_commentators(db, limit=10, offset=0)
    assert [c.user.display_name for c in listed] == ["Fan 0", "Fan 1", "Fan 2"]
