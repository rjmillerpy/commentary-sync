"""Cross-cutting checks for CODE_QUALITY_RULES.md rules 15, 52 and 56."""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = PROJECT_ROOT / "app"
TESTS_ROOT = PROJECT_ROOT / "tests"
MAX_MODULE_LINES = 400

SOURCE_FILES = sorted(path for path in APP_ROOT.rglob("*.py") if path.name != "__init__.py")


def _relative_name(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


@pytest.mark.parametrize("source", SOURCE_FILES, ids=_relative_name)
def test_source_file_has_mirrored_test(source: Path) -> None:
    relative = source.relative_to(APP_ROOT)
    expected = TESTS_ROOT / relative.parent / f"test_{relative.name}"
    assert expected.is_file(), f"missing {_relative_name(expected)}"


@pytest.mark.parametrize("source", SOURCE_FILES, ids=_relative_name)
def test_module_stays_under_line_limit(source: Path) -> None:
    line_count = len(source.read_text().splitlines())
    assert line_count <= MAX_MODULE_LINES


def test_package_markers_stay_empty() -> None:
    """__init__.py files are exempt from the mirror rule only while they hold no code."""
    markers = APP_ROOT.rglob("__init__.py")
    assert all(marker.read_text().strip() == "" for marker in markers)
