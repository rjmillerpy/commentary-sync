import pytest
from pydantic import ValidationError

from app.auth.schema import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Credentials,
    RefreshRequest,
    Registration,
    TokenPair,
)

PASSWORD = "x" * MIN_PASSWORD_LENGTH


def registration(**overrides: str) -> Registration:
    fields = {"email": "fan@example.com", "password": PASSWORD, "display_name": "Fan"}
    return Registration.model_validate({**fields, **overrides})


@pytest.mark.parametrize(
    "password",
    ["x" * MIN_PASSWORD_LENGTH, "x" * MAX_PASSWORD_LENGTH, "é" * MIN_PASSWORD_LENGTH],
    ids=["shortest", "longest", "non-ascii"],
)
def test_accepts_passwords_within_bounds(password: str) -> None:
    assert registration(password=password).password.get_secret_value() == password


@pytest.mark.parametrize(
    "password",
    ["x" * (MIN_PASSWORD_LENGTH - 1), "x" * (MAX_PASSWORD_LENGTH + 1)],
    ids=["too-short", "too-long"],
)
def test_rejects_passwords_out_of_bounds(password: str) -> None:
    with pytest.raises(ValidationError):
        registration(password=password)


def test_display_name_is_trimmed() -> None:
    assert registration(display_name="  Fan  ").display_name == "Fan"


@pytest.mark.parametrize(
    "model",
    [
        registration(),
        Credentials(email="fan@example.com", password=PASSWORD),  # type: ignore[arg-type]
        RefreshRequest(refresh_token=PASSWORD),  # type: ignore[arg-type]
    ],
    ids=["registration", "credentials", "refresh"],
)
def test_secrets_stay_out_of_the_repr(model: object) -> None:
    """Rule 18: a logged request object must not carry the password or token."""
    assert PASSWORD not in repr(model)
    assert PASSWORD not in str(model)


def test_login_does_not_apply_the_password_rules() -> None:
    """An old or short password gets "wrong", not a hint about the rules."""
    assert Credentials.model_validate({"email": "fan@example.com", "password": "short"})


def test_requests_are_immutable() -> None:
    with pytest.raises(ValidationError):
        registration().display_name = "Other"


def test_token_type_is_always_bearer() -> None:
    pair = TokenPair(access_token="a", refresh_token="r", expires_in=900)
    assert pair.token_type == "bearer"
