"""The declarative base every table inherits from, and the way to load them all."""

import importlib
from pathlib import Path

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

APP_ROOT = Path(__file__).resolve().parent.parent
APP_PACKAGE = "app"
MODELS_FILE = "models.py"

# Explicit names for every constraint and index, so a migration can drop or
# alter one by name on any database.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def import_all_models() -> None:
    """Import every domain's models.py so Base.metadata describes the whole schema.

    Migrations compare the database against Base.metadata; a domain that was
    never imported would look like a table to drop. Finding the files here
    means a new domain needs no registration.
    """
    for models_path in sorted(APP_ROOT.glob(f"*/{MODELS_FILE}")):
        domain = models_path.parent.name
        importlib.import_module(f"{APP_PACKAGE}.{domain}.{models_path.stem}")
