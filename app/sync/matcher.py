"""The seam between the app and the matching itself.

The app turns audio into features (service.extract_features) and asks a
Matcher where a query's features sit in a reference's. The `baseline`
(app/sync/baseline.py) ships with the app; another installed package may add
its own under the `commentary_sync.matchers` entry point group.
COMMENTARY_SYNC_MATCHER names the one to use. Unset, the one other installed
matcher is used if there is exactly one, else the baseline.
"""

from functools import cache
from importlib.metadata import entry_points
from typing import Protocol

from app.common.config import MatcherSettings
from app.sync.errors import MatcherNotFoundError
from app.sync.schema import Features, Match

ENTRY_POINT_GROUP = "commentary_sync.matchers"
BASELINE = "baseline"


class Matcher(Protocol):
    """Finds a query inside a reference. Both are already-validated features
    (service.locate_features checks lengths) at service.FRAMES_PER_SECOND."""

    def locate_features(self, reference: Features, query: Features) -> Match: ...


@cache
def _registered() -> dict[str, type[Matcher]]:
    from app.sync.baseline import BaselineMatcher  # it imports the service, which imports this

    installed = {point.name: point.load() for point in entry_points(group=ENTRY_POINT_GROUP)}
    return {BASELINE: BaselineMatcher, **installed}


def available() -> list[str]:
    """Every installed matcher's name, sorted."""
    return sorted(_registered())


def default_name() -> str:
    """The configured matcher, or the one installed besides the baseline, or the baseline."""
    configured = MatcherSettings().sync_matcher
    if configured is not None:
        return configured
    others = [name for name in available() if name != BASELINE]
    return others[0] if len(others) == 1 else BASELINE


def load(name: str | None = None) -> Matcher:
    """The named matcher, or the default one."""
    chosen = default_name() if name is None else name
    registered = _registered()
    if chosen not in registered:
        raise MatcherNotFoundError(
            f"no sync matcher named {chosen!r}; installed: {', '.join(available())}"
        )
    return registered[chosen]()
