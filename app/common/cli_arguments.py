"""Argument validators shared by the command-line interfaces."""

import argparse
from collections.abc import Callable


def bounded_number[Number: (int, float)](
    convert: Callable[[str], Number], minimum: Number, maximum: Number
) -> Callable[[str], Number]:
    """Build an argparse type that accepts a number within a closed range."""

    def parse(text: str) -> Number:
        try:
            value = convert(text)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"{text!r} is not a valid number") from error
        if not minimum <= value <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum:g} and {maximum:g}")
        return value

    return parse
