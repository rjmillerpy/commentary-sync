import pytest
from pydantic import ValidationError

from app.common.pagination import MAX_PAGE_SIZE, Page
from app.common.schema import FrozenModel


class Item(FrozenModel):
    number: int


class ItemPage(Page[Item]):
    pass


def items(count: int) -> list[Item]:
    return [Item(number=number) for number in range(count)]


@pytest.mark.parametrize(
    ("fetched", "limit", "offset", "next_offset"),
    [(3, 3, 0, 3), (3, 3, 6, 9), (2, 3, 6, None), (0, 3, 0, None)],
    ids=["full-first-page", "full-later-page", "short-last-page", "empty"],
)
def test_build_says_where_the_next_page_starts(
    fetched: int, limit: int, offset: int, next_offset: int | None
) -> None:
    page = ItemPage.build(items(fetched), limit=limit, offset=offset)
    assert page.items == items(fetched)
    assert (page.limit, page.offset, page.next_offset) == (limit, offset, next_offset)


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (MAX_PAGE_SIZE + 1, 0), (10, -1)],
    ids=["limit-zero", "limit-over-max", "offset-negative"],
)
def test_page_bounds_are_enforced(limit: int, offset: int) -> None:
    with pytest.raises(ValidationError):
        ItemPage(items=[], limit=limit, offset=offset, next_offset=None)


def test_a_subclass_keeps_its_own_name_in_the_openapi_schema() -> None:
    assert ItemPage.model_json_schema()["title"] == "ItemPage"
