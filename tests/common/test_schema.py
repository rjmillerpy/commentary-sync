from http import HTTPStatus

import pytest
from pydantic import ValidationError

from app.common.schema import ErrorDetail, ErrorResponse, FrozenModel, documented_errors


class Example(FrozenModel):
    name: str


def test_frozen_models_reject_mutation() -> None:
    example = Example(name="first")
    with pytest.raises(ValidationError):
        example.name = "second"


def test_error_response_shape() -> None:
    body = ErrorResponse(detail="Internal server error", request_id="abc12345")
    assert body.model_dump() == {"detail": "Internal server error", "request_id": "abc12345"}


@pytest.mark.parametrize(
    "fields",
    [{"detail": "failed"}, {"request_id": "abc12345"}],
    ids=["no-request-id", "no-detail"],
)
def test_error_response_requires_both_fields(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ErrorResponse(**fields)


def test_error_detail_shape() -> None:
    assert ErrorDetail(detail="Event not found").model_dump() == {"detail": "Event not found"}


def test_documented_errors_name_the_error_model_for_each_status() -> None:
    documented = documented_errors(HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT)
    assert documented == {404: {"model": ErrorDetail}, 409: {"model": ErrorDetail}}
