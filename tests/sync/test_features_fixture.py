"""The fixture the phone's feature extraction is checked against
(client/test/features.test.ts) must be what app/sync computes now."""

import importlib.util
import json
from pathlib import Path

FIXTURE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "client" / "test" / "fixtures" / "features_fixture.py"
)


def test_the_committed_fixture_matches_app_sync() -> None:
    spec = importlib.util.spec_from_file_location("features_fixture", FIXTURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(module.FIXTURE.read_text())
    assert committed == json.loads(json.dumps(module.fixture())), (
        "app/sync's features changed: run `uv run python client/test/fixtures/features_fixture.py`"
    )
