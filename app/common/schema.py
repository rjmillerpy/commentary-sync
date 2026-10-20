"""Schema building blocks shared by every domain."""

from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base for request and response shapes: immutable once built."""

    model_config = ConfigDict(frozen=True)


class ErrorDetail(FrozenModel):
    """What a client sees for an expected failure, such as a missing resource."""

    detail: str


class ValidationIssue(FrozenModel):
    """One thing wrong with a request: its kind, where, and a readable message.
    Never the rejected value, which could be a password."""

    type: str
    loc: tuple[str | int, ...]
    msg: str


class ValidationErrorResponse(FrozenModel):
    """What a client sees for a 422."""

    detail: tuple[ValidationIssue, ...]


class ErrorResponse(FrozenModel):
    """What a client sees when a request fails unexpectedly."""

    detail: str
    request_id: str


def documented_errors(*statuses: HTTPStatus) -> dict[int | str, dict[str, Any]]:
    """A route's `responses=`: these statuses return an ErrorDetail (rule 46)."""
    return {status.value: {"model": ErrorDetail} for status in statuses}
