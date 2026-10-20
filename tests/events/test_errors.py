import pytest

from app.events.errors import (
    EventNotFoundError,
    EventsError,
    EventSourceError,
    InvalidImportWindowError,
)


@pytest.mark.parametrize(
    "error_type",
    [EventSourceError, InvalidImportWindowError, EventNotFoundError],
    ids=["source", "window", "not-found"],
)
def test_every_error_is_an_events_error(error_type: type[EventsError]) -> None:
    """Callers can catch the whole domain with one except clause."""
    assert issubclass(error_type, EventsError)
