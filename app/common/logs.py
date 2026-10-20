"""Log output: one JSON object per line, for every process the app runs.

Code logs through the standard library, `logging.getLogger(__name__)`, as
before, so every app logger is under `app`. Here structlog only renders the
records, adding the time, level, logger name, the request context bound in
app.common.request_tracing (request ID, account ID) and any `extra={...}`
fields:

    {"timestamp": "2026-10-15T16:11:16.799Z", "level": "warning",
     "logger": "app.common.rate_limit", "request_id": "40161dce...",
     "message": "rate limit auth-login-minute exceeded"}

`console` renders the same fields as readable text for local work.
"""

import logging
import sys
from typing import Literal, TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LogFormat = Literal["json", "console"]

# uvicorn installs its own handlers; its lines are routed through ours instead.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
# Replaced by the access line app.common.request_tracing writes, which has the
# request ID and duration and leaves out the client's IP address.
UVICORN_ACCESS_LOGGER = "uvicorn.access"
# The configured level applies to these. Every other library logs warnings
# and errors only, whatever the level: at debug and info, libraries log what
# they handle (the HTTP client every URL with its query string, database
# drivers every statement with its parameters), which can be passwords,
# tokens or emails (rule 18).
LEVEL_CONTROLLED_LOGGERS = ("app", "alembic", "uvicorn")
LIBRARY_LEVEL = logging.WARNING

# uvicorn adds a copy of some messages with terminal colour codes in them.
UVICORN_COLOR_FIELD = "color_message"


def _drop_uvicorn_color_message(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    return {key: value for key, value in event_dict.items() if key != UVICORN_COLOR_FIELD}


# Fields every line gets, before the format-specific rendering.
_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.ExtraAdder(),
    _drop_uvicorn_color_message,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
]


class AppLogHandler(logging.StreamHandler[TextIO]):
    """The handler configure_logging installs, so it can find and replace its own."""


def configure_logging(
    level: str, log_format: LogFormat = "json", stream: TextIO | None = None
) -> None:
    """Send every log record to `stream` (stderr by default) in `log_format`.

    Safe to call more than once: the previous AppLogHandler is replaced, and
    handlers others installed (pytest's, for example) are left alone.
    """
    root = logging.getLogger()
    for handler in [handler for handler in root.handlers if isinstance(handler, AppLogHandler)]:
        root.removeHandler(handler)
    handler = AppLogHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(_formatter(log_format))
    root.addHandler(handler)
    root.setLevel(LIBRARY_LEVEL)
    for name in LEVEL_CONTROLLED_LOGGERS:
        logging.getLogger(name).setLevel(level)

    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger(UVICORN_ACCESS_LOGGER).disabled = True


def _formatter(log_format: LogFormat) -> structlog.stdlib.ProcessorFormatter:
    renderers: dict[LogFormat, list[Processor]] = {
        "json": [
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ],
        "console": [structlog.dev.ConsoleRenderer(colors=False)],
    }
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta]
        + renderers[log_format],
    )
