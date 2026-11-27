"""The rendered-pictures model as fixtures: built once per worker, copied for each test that writes.

Registered for the whole suite through `pytest_plugins` in `tests/conftest.py`. The imports are
deferred so loading the plugin costs nothing for the tests that never ask for the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.support.rendered_pictures import RenderedModel


@pytest.fixture(scope="session")
def rendered_model_original(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    """The model of `tests.support.rendered_pictures`, built once per worker.

    Building it writes the model through MCP and draws every scene through PlantUML, which was most
    of what each test using it paid. Nothing may write to this one: a test that writes takes a copy
    of its own through `rendered_model`.
    """
    from tests.support.rendered_pictures import build_rendered_model  # noqa: PLC0415

    return build_rendered_model(tmp_path_factory.mktemp("rendered-model"))


@pytest.fixture
def rendered_model(rendered_model_original: RenderedModel, tmp_path: Path) -> RenderedModel:
    """A copy of the rendered-pictures model of this test's own, to write to as it likes."""
    from tests.support.rendered_pictures import copy_rendered_model  # noqa: PLC0415

    return copy_rendered_model(rendered_model_original, tmp_path)
