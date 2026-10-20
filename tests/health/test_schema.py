import pytest
from pydantic import ValidationError

from app.health.schema import HealthStatus, LivenessResponse, ReadinessChecks, ReadinessResponse


@pytest.mark.parametrize(
    ("member", "wire_value"),
    [(HealthStatus.OK, "ok"), (HealthStatus.UNAVAILABLE, "unavailable")],
    ids=["ok", "unavailable"],
)
def test_wire_values_are_stable(member: HealthStatus, wire_value: str) -> None:
    """Load balancers and dashboards match on these strings."""
    assert member.value == wire_value


def test_liveness_shape() -> None:
    assert LivenessResponse(status=HealthStatus.OK).model_dump(mode="json") == {"status": "ok"}


def test_readiness_shape() -> None:
    response = ReadinessResponse(
        status=HealthStatus.UNAVAILABLE,
        checks=ReadinessChecks(database=HealthStatus.OK, cache=HealthStatus.UNAVAILABLE),
    )
    assert response.model_dump(mode="json") == {
        "status": "unavailable",
        "checks": {"database": "ok", "cache": "unavailable"},
    }


def test_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        LivenessResponse.model_validate({"status": "degraded"})


def test_responses_are_immutable() -> None:
    response = LivenessResponse(status=HealthStatus.OK)
    with pytest.raises(ValidationError):
        response.status = HealthStatus.UNAVAILABLE
