"""Offset pagination shared by every list endpoint.

class ThingPage(Page[ThingResponse]): ...  # a subclass keeps a readable OpenAPI name

@router.get("")
async def list_things(limit: PageLimit = DEFAULT_PAGE_SIZE, offset: PageOffset = 0):
    return ThingPage.build(items, limit=limit, offset=offset)
"""

from collections.abc import Sequence
from typing import Annotated, Self

from fastapi import Query
from pydantic import Field

from app.common.schema import FrozenModel

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000  # deeper than anyone pages; keeps OFFSET scans bounded

PageLimit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
PageOffset = Annotated[int, Query(ge=0, le=MAX_OFFSET)]


class Page[Item](FrozenModel):
    """One page of a list, and where the next one starts."""

    items: list[Item]
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(ge=0)
    next_offset: int | None  # None on the last page

    @classmethod
    def build(cls, items: Sequence[Item], *, limit: int, offset: int) -> Self:
        """A page of `items`, fetched with this limit and offset.

        A short page is the last one. A full page may be followed by an empty
        one, which costs a client one extra request but the server no count query.
        """
        is_last_page = len(items) < limit
        return cls(
            items=list(items),
            limit=limit,
            offset=offset,
            next_offset=None if is_last_page else offset + limit,
        )
