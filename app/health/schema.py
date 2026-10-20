"""Response shapes for the health endpoints."""

from enum import StrEnum

from app.common.schema import FrozenModel


class HealthStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class LivenessResponse(FrozenModel):
    status: HealthStatus


class ReadinessChecks(FrozenModel):
    database: HealthStatus
    cache: HealthStatus


class ReadinessResponse(FrozenModel):
    status: HealthStatus
    checks: ReadinessChecks
