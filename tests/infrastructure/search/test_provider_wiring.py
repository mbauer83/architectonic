"""A deployment without the branch must answer exactly as it always has, and be told why.

Three conditions turn it off — not asked for, weights not usable, weights would not load — and none
of them may raise: keyword search is the whole of what the product promises without vector
retrieval, so a failure here degrades rather than breaks. Each condition also has to say once, at a
level an operator reads, which one it was; an operator who turned the setting on and saw no change
must be able to find out that the asset is missing without reading the source.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.config import settings
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.search import provider as provider_module
from src.infrastructure.search.provider import semantic_provider_for
from tests.support.search_visibility_fixtures import entity_md, write_file

_ENTITY = "REQ@1000000501.Wiring.a-requirement"


@pytest.fixture(autouse=True)
def _forget_the_process_encoder() -> None:
    """The encoder is cached per process; each test states its own conditions."""
    provider_module._process_encoder.cache_clear()


@pytest.fixture
def store(tmp_path: Path):  # noqa: ANN201 — the index type is internal to the fixture
    root = tmp_path / "engagements" / "ENG-WIRE" / "architecture-repository"
    write_file(
        root / "model" / "motivation" / "requirement" / f"{_ENTITY}.md",
        entity_md(_ENTITY, "requirement", "A Requirement", body="promotion across tiers"),
    )
    index = shared_artifact_index(root)
    index.refresh()
    return index


def _configure(monkeypatch: pytest.MonkeyPatch, semantic_search: object) -> None:
    """Replace the loader with a fixed answer, built before it is replaced."""
    loaded = settings.load_settings()
    storage = {**dict(loaded["storage"]), "read_model": {"semantic_search": semantic_search}}  # type: ignore[arg-type]
    configured = {**loaded, "storage": storage}
    monkeypatch.setattr(settings, "load_settings", lambda: configured)


def test_a_deployment_that_did_not_ask_for_it_gets_nothing(monkeypatch: pytest.MonkeyPatch, store) -> None:  # noqa: ANN001
    _configure(monkeypatch, False)
    assert semantic_provider_for(store) is None


def test_off_is_the_default(monkeypatch: pytest.MonkeyPatch, store) -> None:  # noqa: ANN001
    """A deployment that says nothing must not acquire the branch by upgrading."""
    monkeypatch.setattr(settings, "load_settings", lambda: settings._DEFAULTS)
    assert semantic_provider_for(store) is None


def test_anything_that_is_not_true_is_off(monkeypatch: pytest.MonkeyPatch, store) -> None:  # noqa: ANN001
    """A capability turned on by a typo would be the wrong way for this to fail."""
    for value in ("true", "yes", 1, "on", None, {}):
        provider_module._process_encoder.cache_clear()
        _configure(monkeypatch, value)
        assert semantic_provider_for(store) is None, value


def test_missing_weights_degrade_to_keyword_search_and_say_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path, store  # noqa: ANN001
) -> None:
    _configure(monkeypatch, True)
    monkeypatch.setenv("ARCH_EMBEDDING_MODEL_DIR", str(tmp_path / "not-installed"))
    with caplog.at_level(logging.WARNING):
        assert semantic_provider_for(store) is None
    assert "get-embedding-model" in caplog.text
    assert "keyword" in caplog.text


def test_a_model_that_will_not_load_degrades_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, store  # noqa: ANN001
) -> None:
    """Everything past the integrity check is the library's business, and it may still fail."""
    _configure(monkeypatch, True)
    monkeypatch.setattr(provider_module, "integrity_failures", lambda: ())
    monkeypatch.setattr(
        provider_module,
        "StaticEmbeddingEncoder",
        lambda directory: (_ for _ in ()).throw(RuntimeError("weights are gibberish")),
    )
    with caplog.at_level(logging.WARNING):
        assert semantic_provider_for(store) is None
    assert "gibberish" in caplog.text


def test_the_encoder_is_loaded_once_per_process(monkeypatch: pytest.MonkeyPatch, store) -> None:  # noqa: ANN001
    """A backend serving two repository roots should read 30 MB once, not twice."""
    _configure(monkeypatch, True)
    monkeypatch.setattr(provider_module, "integrity_failures", lambda: ())
    loads: list[Path] = []

    class Encoder:
        def __init__(self, directory: Path) -> None:
            loads.append(directory)

        def encode(self, passages: list[str]):  # noqa: ANN201 — shape fixed by the caller
            import numpy as np

            return np.zeros((len(passages), 2), dtype=np.float32)

        @property
        def dimensions(self) -> int:
            return 2

    monkeypatch.setattr(provider_module, "StaticEmbeddingEncoder", Encoder)
    assert semantic_provider_for(store) is not None
    assert semantic_provider_for(store) is not None
    assert len(loads) == 1


def test_each_store_gets_its_own_matrix(monkeypatch: pytest.MonkeyPatch, store, tmp_path: Path) -> None:  # noqa: ANN001
    """Sharing one across stores is how a query is answered from a neighbouring checkout's model."""
    _configure(monkeypatch, True)
    monkeypatch.setattr(provider_module, "integrity_failures", lambda: ())

    class Encoder:
        def encode(self, passages: list[str]):  # noqa: ANN201
            import numpy as np

            return np.zeros((len(passages), 2), dtype=np.float32)

        @property
        def dimensions(self) -> int:
            return 2

    monkeypatch.setattr(provider_module, "StaticEmbeddingEncoder", lambda directory: Encoder())

    other_root = tmp_path / "engagements" / "ENG-OTHER" / "architecture-repository"
    write_file(
        other_root / "model" / "motivation" / "requirement" / f"{_ENTITY}.md",
        entity_md(_ENTITY, "requirement", "A Requirement", body="one two three four five six"),
    )
    other = shared_artifact_index(other_root)
    other.refresh()

    first = semantic_provider_for(store)
    second = semantic_provider_for(other)
    assert first is not None and second is not None
    assert first is not second
