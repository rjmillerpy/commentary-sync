import pytest

from app.streams.errors import (
    AlreadyLiveError,
    EventOverError,
    NotRecordingError,
    RecorderError,
    StreamEndedError,
    StreamNotFoundError,
    StreamsError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        StreamNotFoundError,
        AlreadyLiveError,
        EventOverError,
        StreamEndedError,
        RecorderError,
        NotRecordingError,
    ],
    ids=lambda error_type: error_type.__name__,
)
def test_every_streams_error_is_a_streams_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, StreamsError)
