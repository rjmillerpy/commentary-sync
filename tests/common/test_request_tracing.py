import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.request_tracing import (
    NO_REQUEST_ID,
    REQUEST_ID_HEADER,
    bind_account,
    current_request_id,
)
from app.common.schema import FrozenModel
from tests.conftest import LogLines

logger = logging.getLogger("app.tests.request_tracing")  # under `app`, so info is kept

GENERATED_ID_LENGTH = 32  # uuid4().hex
ACCOUNT = uuid.UUID("6f1c2a52-0d9e-4c55-9a43-2b8f3e1d7c60")


class TracedResponse(FrozenModel):
    request_id: str


@pytest.fixture
def traced(app: FastAPI, client: TestClient) -> TestClient:
    @app.get("/log-something")
    async def log_something() -> TracedResponse:
        logger.info("inside the request")
        return TracedResponse(request_id=current_request_id())

    @app.get("/signed-in")
    async def signed_in() -> TracedResponse:
        bind_account(ACCOUNT)
        logger.info("as an account")
        return TracedResponse(request_id=current_request_id())

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    return client


def lines_with(lines: list[dict[str, object]], message: str) -> list[dict[str, object]]:
    return [line for line in lines if line["message"] == message]


def test_every_response_carries_a_generated_id(client: TestClient) -> None:
    first = client.get("/health/live").headers[REQUEST_ID_HEADER]
    second = client.get("/health/live").headers[REQUEST_ID_HEADER]
    assert len(first) == GENERATED_ID_LENGTH
    assert first != second


@pytest.mark.parametrize(
    "supplied",
    ["abcd1234", "trace-2026-10-07-000123", "A" * 64],
    ids=["shortest", "with-dashes", "longest"],
)
def test_well_formed_caller_id_is_kept(client: TestClient, supplied: str) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] == supplied


@pytest.mark.parametrize(
    "supplied",
    ["short", "A" * 65, "has spaces in it", "semi;colon;id", "<script>alert(1)</script>", ""],
    ids=["too-short", "too-long", "spaces", "punctuation", "markup", "empty"],
)
def test_malformed_caller_id_is_replaced(client: TestClient, supplied: str) -> None:
    """The ID reaches logs and a response header, so only plain tokens are accepted."""
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] != supplied
    assert len(response.headers[REQUEST_ID_HEADER]) == GENERATED_ID_LENGTH


def test_log_lines_inside_a_request_carry_its_id(traced: TestClient, log_lines: LogLines) -> None:
    response = traced.get("/log-something")
    request_id = response.headers[REQUEST_ID_HEADER]
    [line] = lines_with(log_lines(), "inside the request")
    assert line["request_id"] == request_id
    assert line["account_id"] is None  # nobody signed in
    assert TracedResponse.model_validate(response.json()).request_id == request_id


def test_a_bound_account_is_on_later_lines(traced: TestClient, log_lines: LogLines) -> None:
    traced.get("/signed-in")
    [line] = lines_with(log_lines(), "as an account")
    assert line["account_id"] == str(ACCOUNT)
    [access] = lines_with(log_lines(), "GET /signed-in 200")
    assert access["account_id"] == str(ACCOUNT)


def test_regression_context_does_not_leak_into_the_next_request(
    traced: TestClient, log_lines: LogLines
) -> None:
    """Regression: an account bound in one request must not be named on the
    next request's lines."""
    traced.get("/signed-in")
    second = traced.get("/log-something")
    [line] = lines_with(log_lines(), "inside the request")
    assert line["account_id"] is None
    assert line["request_id"] == second.headers[REQUEST_ID_HEADER]
    assert current_request_id() == NO_REQUEST_ID


def test_each_request_gets_one_access_line(traced: TestClient, log_lines: LogLines) -> None:
    response = traced.get("/log-something", params={"token": "secret-in-query"})
    [access] = [line for line in log_lines() if line["logger"] == "app.access"]
    assert access["message"] == "GET /log-something 200"
    assert access["method"] == "GET"
    assert access["path"] == "/log-something"
    assert access["status"] == 200
    assert isinstance(access["duration_ms"], float)
    assert access["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert access["level"] == "info"


def test_access_lines_leave_out_the_query_and_the_client_address(
    traced: TestClient, log_lines: LogLines
) -> None:
    """Rule 18: a query string can carry tokens, and an IP address is personal data."""
    traced.get("/log-something", params={"token": "secret-in-query"})
    written = str(log_lines())
    assert "secret-in-query" not in written
    assert "testclient" not in written  # the test client's address


def test_a_failed_request_is_logged_as_500(traced: TestClient, log_lines: LogLines) -> None:
    assert traced.get("/explode").status_code == 500
    [access] = lines_with(log_lines(), "GET /explode 500")
    assert access["status"] == 500


@pytest.mark.parametrize(
    ("path", "level"),
    [("/health/live", "debug"), ("/health", "debug"), ("/log-something", "info")],
    ids=["liveness-probe", "readiness-probe", "ordinary-route"],
)
def test_health_probes_log_at_debug(
    traced: TestClient, log_lines: LogLines, path: str, level: str
) -> None:
    """Docker and the load balancer probe every few seconds; info would bury real traffic."""
    traced.get(path)
    [access] = [line for line in log_lines() if line["logger"] == "app.access"]
    assert access["level"] == level


def test_no_request_id_outside_a_request(client: TestClient) -> None:
    client.get("/health/live")
    assert current_request_id() == NO_REQUEST_ID
