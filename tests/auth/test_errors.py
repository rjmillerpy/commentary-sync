import pytest

from app.auth.errors import (
    AuthError,
    AuthUnavailableError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    LoginLockedError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        EmailTakenError,
        InvalidCredentialsError,
        InvalidTokenError,
        AuthUnavailableError,
        LoginLockedError,
    ],
    ids=lambda error_type: error_type.__name__,
)
def test_every_auth_error_is_an_auth_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, AuthError)


def test_a_lockout_says_how_long_it_lasts() -> None:
    error = LoginLockedError(42)
    assert error.retry_after_seconds == 42
    assert "42" in str(error)
