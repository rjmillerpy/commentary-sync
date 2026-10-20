"""Errors the auth domain reports to its callers."""


class AuthError(Exception):
    """Base class: anything the auth domain can fail with."""


class EmailTakenError(AuthError):
    """An account already uses this email address."""


class InvalidCredentialsError(AuthError):
    """The email and password don't match an account. Which of the two is
    wrong is deliberately not said."""


class LoginLockedError(AuthError):
    """Too many wrong passwords for this account; try again later."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"login locked for {retry_after_seconds} s")
        self.retry_after_seconds = retry_after_seconds


class InvalidTokenError(AuthError):
    """An access or refresh token is malformed, expired, revoked or forged."""


class AuthUnavailableError(AuthError):
    """A store auth depends on (Redis for the lockout) can't be reached."""
