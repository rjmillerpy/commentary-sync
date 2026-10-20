import io
import json
import logging
from collections.abc import Iterator

import pytest

from app.common.logs import (
    LIBRARY_LEVEL,
    UVICORN_ACCESS_LOGGER,
    UVICORN_LOGGERS,
    AppLogHandler,
    LogFormat,
    configure_logging,
)

# Under `app`, like every app logger: the configured level applies to it.
logger = logging.getLogger("app.tests.logs")


@pytest.fixture
def buffer() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    yield stream
    configure_logging("INFO")  # back to stderr for whatever runs next


def written(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_each_record_is_one_json_line(buffer: io.StringIO) -> None:
    configure_logging("INFO", "json", buffer)
    logger.info("imported %d games", 14)
    [line] = written(buffer)
    assert line["message"] == "imported 14 games"
    assert line["level"] == "info"
    assert line["logger"] == "app.tests.logs"
    assert str(line["timestamp"]).endswith("Z")  # UTC


def test_extra_fields_become_json_fields(buffer: io.StringIO) -> None:
    configure_logging("INFO", "json", buffer)
    logger.info("cycle done", extra={"league": "nfl", "fetched": 14})
    [line] = written(buffer)
    assert line["league"] == "nfl"
    assert line["fetched"] == 14


def test_an_exception_is_kept_with_its_line(buffer: io.StringIO) -> None:
    """A traceback stays inside its JSON object instead of spilling over many lines."""
    configure_logging("INFO", "json", buffer)
    try:
        raise ValueError("bad value")
    except ValueError:
        logger.exception("import failed")
    [line] = written(buffer)
    assert line["message"] == "import failed"
    assert "ValueError: bad value" in str(line["exception"])


@pytest.mark.parametrize(
    ("level", "shown"),
    [("DEBUG", ["debug", "info"]), ("INFO", ["info"]), ("WARNING", [])],
    ids=["debug", "info", "warning"],
)
def test_the_level_filters_records(buffer: io.StringIO, level: str, shown: list[str]) -> None:
    configure_logging(level, "json", buffer)
    logger.debug("detail")
    logger.info("progress")
    assert [line["level"] for line in written(buffer)] == shown


def test_console_format_is_readable_text(buffer: io.StringIO) -> None:
    configure_logging("INFO", "console", buffer)
    logger.warning("rate limit exceeded")
    text = buffer.getvalue()
    assert "rate limit exceeded" in text
    assert "warning" in text
    assert not text.lstrip().startswith("{")


@pytest.mark.parametrize("log_format", ["json", "console"], ids=["json", "console"])
def test_configuring_again_replaces_only_its_own_handler(
    buffer: io.StringIO, log_format: LogFormat
) -> None:
    """Called by every process start and every create_app: never two app
    handlers, and other handlers (pytest's) stay."""
    foreign = logging.NullHandler()
    logging.getLogger().addHandler(foreign)
    try:
        configure_logging("INFO", log_format, io.StringIO())
        configure_logging("INFO", log_format, buffer)
        handlers = logging.getLogger().handlers
        assert len([h for h in handlers if isinstance(h, AppLogHandler)]) == 1
        assert foreign in handlers
    finally:
        logging.getLogger().removeHandler(foreign)


def test_uvicorn_lines_come_through_the_app_handler(buffer: io.StringIO) -> None:
    configure_logging("INFO", "json", buffer)
    for name in UVICORN_LOGGERS:
        assert logging.getLogger(name).handlers == []
        logging.getLogger(name).info("from %s", name)
    assert [line["logger"] for line in written(buffer)] == list(UVICORN_LOGGERS)


def test_uvicorn_access_lines_are_off(buffer: io.StringIO) -> None:
    """app.access replaces them; uvicorn's include the client's IP address."""
    configure_logging("INFO", "json", buffer)
    logging.getLogger(UVICORN_ACCESS_LOGGER).info('203.0.113.7 - "GET / HTTP/1.1" 200')
    assert written(buffer) == []


@pytest.mark.parametrize(
    ("library", "message"),
    [
        ("httpx2", "HTTP Request: GET https://api.example.com/?apiKey=k"),
        ("aiosqlite", "INSERT INTO users (email, password_hash) ('fan@example.com', '$argon2')"),
        ("sqlalchemy.engine", "SELECT users.email FROM users"),
    ],
    ids=["http-client-urls", "driver-parameters", "orm-statements"],
)
def test_regression_libraries_log_only_warnings_even_at_debug(
    buffer: io.StringIO, library: str, message: str
) -> None:
    """Regression: at debug, httpx2 logged every URL with its query string and
    aiosqlite every statement with its parameters, emails and password hashes
    included. Libraries now log warnings and errors only, at any level."""
    configure_logging("DEBUG", "json", buffer)
    logging.getLogger(library).debug(message)
    logging.getLogger(library).info(message)
    logging.getLogger(library).warning("connection reset")
    assert [line["message"] for line in written(buffer)] == ["connection reset"]
    assert logging.getLogger().level == LIBRARY_LEVEL


def test_uvicorn_colour_codes_are_dropped(buffer: io.StringIO) -> None:
    configure_logging("INFO", "json", buffer)
    logging.getLogger("uvicorn.error").info(
        "Uvicorn running", extra={"color_message": "\x1b[1mUvicorn running\x1b[0m"}
    )
    [line] = written(buffer)
    assert "color_message" not in line
