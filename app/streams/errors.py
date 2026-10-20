"""Errors the streams domain reports to its callers."""


class StreamsError(Exception):
    """Base class: anything the streams domain can fail with."""


class StreamNotFoundError(StreamsError):
    """No stream has this ID, or (when ending one) it belongs to someone else."""


class AlreadyLiveError(StreamsError):
    """The commentator already has a live stream; end it first."""


class EventOverError(StreamsError):
    """The event is final, cancelled or postponed, so no one can go live on it."""


class StreamEndedError(StreamsError):
    """The stream has already ended."""


class WebhookSignatureError(StreamsError):
    """A webhook that LiveKit didn't sign, or whose body was changed."""


class WebhookPayloadError(StreamsError):
    """A signed webhook whose body isn't a notice this API understands."""


class RecorderError(StreamsError):
    """LiveKit Egress didn't start or stop a recording: unreachable, or it said no."""


class NotRecordingError(StreamsError):
    """The stream has no HLS recording: its commentator hasn't connected yet,
    the recorder couldn't start, or HLS is off."""


class SyncAudioError(StreamsError):
    """Audio sent for sync that can't be used: unreadable, too short or too long."""


class CaptureTimeError(StreamsError):
    """Audio stamped with a capture time too far from the server's clock."""
