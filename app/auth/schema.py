"""Request and response shapes for auth."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, SecretStr, StringConstraints

from app.auth.models import MAX_DISPLAY_NAME_LENGTH
from app.common.schema import FrozenModel

MIN_PASSWORD_LENGTH = 12
# Hashing cost doesn't grow with length, but the request body should stay small.
MAX_PASSWORD_LENGTH = 256
MAX_REFRESH_TOKEN_LENGTH = 128

# SecretStr: a password or token never shows up in a repr, a log line or an error.
NewPassword = Annotated[
    SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_DISPLAY_NAME_LENGTH)
]


class Registration(FrozenModel):
    email: EmailStr
    password: NewPassword
    display_name: DisplayName


class Credentials(FrozenModel):
    email: EmailStr
    # No minimum here: a login reports only "wrong", never the password rules.
    password: Annotated[SecretStr, Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)]


class RefreshRequest(FrozenModel):
    refresh_token: Annotated[SecretStr, Field(min_length=1, max_length=MAX_REFRESH_TOKEN_LENGTH)]


class TokenPair(FrozenModel):
    """What a successful sign-in returns. Send the access token as
    `Authorization: Bearer ...`. It lasts `expires_in` seconds; after that,
    trade the refresh token for a new pair."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # the OAuth 2 scheme name, not a secret
    expires_in: int


class UserResponse(FrozenModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime
