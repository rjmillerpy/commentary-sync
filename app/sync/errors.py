"""Errors the sync domain reports to its callers."""


class SyncError(Exception):
    """Base class: anything the sync domain can fail with."""


class AudioDecodeError(SyncError):
    """An audio source could not be read."""


class AudioEncodeError(SyncError):
    """Audio could not be written."""


class InvalidAudioError(SyncError):
    """Audio was readable but unusable, for example too short to analyse."""


class MatcherNotFoundError(SyncError):
    """The configured matcher is not installed."""
