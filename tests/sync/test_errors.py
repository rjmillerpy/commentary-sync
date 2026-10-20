import pytest

from app.sync.errors import (
    AudioDecodeError,
    AudioEncodeError,
    InvalidAudioError,
    MatcherNotFoundError,
    SyncError,
)


@pytest.mark.parametrize(
    "error_type",
    [AudioDecodeError, AudioEncodeError, InvalidAudioError, MatcherNotFoundError],
    ids=lambda error_type: error_type.__name__,
)
def test_domain_errors_share_one_base_and_keep_their_message(
    error_type: type[SyncError],
) -> None:
    error = error_type("what went wrong")
    assert isinstance(error, SyncError)
    assert str(error) == "what went wrong"
