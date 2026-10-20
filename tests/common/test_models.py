import sys
from pathlib import Path

import pytest

from app.common.models import APP_ROOT, NAMING_CONVENTION, Base, import_all_models


def test_every_models_file_is_loaded_into_the_metadata() -> None:
    """A domain that was never imported would look, to a migration, like a table to drop."""
    import_all_models()
    expected = {f"app.{path.parent.name}.models" for path in APP_ROOT.glob("*/models.py")}
    assert expected <= set(sys.modules)
    assert "events" in Base.metadata.tables


def test_importing_twice_is_harmless() -> None:
    import_all_models()
    tables_before = set(Base.metadata.tables)
    import_all_models()
    assert set(Base.metadata.tables) == tables_before


@pytest.mark.parametrize(
    "kind",
    ["ix", "uq", "ck", "fk", "pk"],
    ids=["index", "unique", "check", "foreign-key", "primary-key"],
)
def test_every_constraint_kind_gets_an_explicit_name(kind: str) -> None:
    assert kind in NAMING_CONVENTION
    assert kind in Base.metadata.naming_convention


def test_app_root_is_the_app_package() -> None:
    assert Path(APP_ROOT, "main.py").is_file()
