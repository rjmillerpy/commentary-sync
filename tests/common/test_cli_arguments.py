import argparse

import pytest

from app.common.cli_arguments import bounded_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", 1.0), ("2.5", 2.5), ("10", 10.0)],
    ids=["lower-bound", "inside", "upper-bound"],
)
def test_accepts_numbers_inside_the_range(text: str, expected: float) -> None:
    assert bounded_number(float, 1.0, 10.0)(text) == expected


@pytest.mark.parametrize(
    "text",
    ["0.99", "10.01", "-3", "abc", "", "nan"],
    ids=["below", "above", "negative", "not-a-number", "empty", "nan"],
)
def test_rejects_numbers_outside_the_range(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        bounded_number(float, 1.0, 10.0)(text)


def test_integer_conversion_rejects_fractions() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        bounded_number(int, 1, 10)("2.5")
