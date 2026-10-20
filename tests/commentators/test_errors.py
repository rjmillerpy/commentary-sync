import pytest

from app.commentators.errors import (
    AlreadyCommentatorError,
    CommentatorNotFoundError,
    CommentatorsError,
    HandleTakenError,
    NotACommentatorError,
)


@pytest.mark.parametrize(
    "error_type",
    [AlreadyCommentatorError, HandleTakenError, NotACommentatorError, CommentatorNotFoundError],
    ids=lambda error_type: error_type.__name__,
)
def test_every_commentators_error_is_a_commentators_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, CommentatorsError)
