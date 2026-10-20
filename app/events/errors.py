"""Errors the events domain reports to its callers."""


class EventsError(Exception):
    """Base class: anything the events domain can fail with."""


class EventSourceError(EventsError):
    """The schedule provider could not be reached or sent something unusable."""


class InvalidImportWindowError(EventsError):
    """An import was asked for a range of days outside what is allowed."""


class EventNotFoundError(EventsError):
    """No event has the requested ID."""
