"""Request and response shapes for commentators."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints

from app.commentators.models import MAX_BIO_LENGTH, MAX_HANDLE_LENGTH
from app.common.pagination import Page
from app.common.schema import FrozenModel

# Longer than "me", so no handle can shadow GET /commentators/me.
MIN_HANDLE_LENGTH = 3
# ASCII letters, digits and underscores: safe in a URL path as it is. Stored
# lower-case; pydantic checks the pattern before lowering, so it allows both.
HANDLE_PATTERN = r"^[A-Za-z0-9_]+$"


# "Bob" is accepted and stored as "bob".
Handle = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=MIN_HANDLE_LENGTH,
        max_length=MAX_HANDLE_LENGTH,
        pattern=HANDLE_PATTERN,
    ),
]
Bio = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_BIO_LENGTH)]


class CommentatorSignup(FrozenModel):
    """Become a commentator. The handle can't be changed later, so a link to
    a commentator never starts pointing at someone else."""

    handle: Handle
    bio: Bio = ""


class ProfileUpdate(FrozenModel):
    bio: Bio


class CommentatorResponse(FrozenModel):
    """A commentator as anyone sees them. No email: the profile is public."""

    id: uuid.UUID
    handle: str
    display_name: str
    bio: str
    created_at: datetime


class CommentatorPage(Page[CommentatorResponse]):
    """One page of commentators in handle order."""
