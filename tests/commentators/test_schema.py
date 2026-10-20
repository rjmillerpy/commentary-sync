import pytest
from pydantic import ValidationError

from app.commentators.models import MAX_BIO_LENGTH, MAX_HANDLE_LENGTH
from app.commentators.schema import CommentatorSignup, ProfileUpdate


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("fan_cast", "fan_cast"),
        ("  FanCast99 ", "fancast99"),
        ("abc", "abc"),
        ("a" * MAX_HANDLE_LENGTH, "a" * MAX_HANDLE_LENGTH),
    ],
    ids=["plain", "mixed-case-and-padding", "shortest", "longest"],
)
def test_handles_are_accepted_in_lower_case(given: str, stored: str) -> None:
    assert CommentatorSignup(handle=given).handle == stored


@pytest.mark.parametrize(
    "handle",
    ["ab", "a" * (MAX_HANDLE_LENGTH + 1), "fan cast", "fan-cast", "fan/cast", "fän", "me", ""],
    ids=[
        "too-short",
        "too-long",
        "space",
        "hyphen",
        "slash",
        "non-ascii",
        "me-the-own-profile-path",
        "empty",
    ],
)
def test_bad_handles_are_rejected(handle: str) -> None:
    with pytest.raises(ValidationError):
        CommentatorSignup(handle=handle)


def test_bio_defaults_to_empty_and_is_trimmed() -> None:
    assert CommentatorSignup(handle="fan_cast").bio == ""
    assert ProfileUpdate(bio="  Bears, every snap.  ").bio == "Bears, every snap."


def test_bio_has_a_length_limit() -> None:
    ProfileUpdate(bio="x" * MAX_BIO_LENGTH)
    with pytest.raises(ValidationError):
        ProfileUpdate(bio="x" * (MAX_BIO_LENGTH + 1))
