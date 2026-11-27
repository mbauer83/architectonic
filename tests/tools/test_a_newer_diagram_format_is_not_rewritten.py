"""C.5b: a product does not rewrite a diagram a newer product wrote, so it cannot drop what it does not know.

Before this, nothing compared a diagram's `diagram-format-version` with what the running type writes:
an edit carried an unknown `diagram-entities` key only if the caller sent it back (the MCP edit
replaces the block whole), renderers leave out what they do not draw, and the data-type writer stamped
a hard-coded `2` over whatever the file said — destroying the evidence that it was newer. A type now
declares the version it writes, a write stamps it, and a rewrite of a higher version is refused.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.diagrams.diagram_format_version import (
    newer_format_refusal,
    stated_format_version,
    version_to_stamp,
)
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram


@lru_cache(maxsize=1)
def _catalogs():  # noqa: ANN202 - the runtime catalogs, built once
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _sequence_diagram(repo_root: Path, version: int | None) -> str:
    artifact_id = "SEQ@1.a.newer"
    stated = f"diagram-format-version: {version}\n" if version is not None else ""
    path = repo_root / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "model").mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nartifact-id: {artifact_id}\nartifact-type: diagram\nname: Newer\nversion: 0.1.0\nstatus: draft\n"
        f"diagram-type: sequence\n{stated}diagram-entities:\n  lifeline:\n  - id: a\n    label: A\n"
        "  interaction_use_from_the_future:\n  - id: r1\n    label: Elsewhere\n"
        "last-updated: '2026-01-01'\n---\n@startuml newer\nparticipant \"A\" as a\n@enduml\n",
        encoding="utf-8",
    )
    return artifact_id


def _edit(repo_root: Path, artifact_id: str) -> object:
    return edit_diagram(
        assert_write_root=assert_engagement_write_root,
        repo_root=repo_root,
        verifier=ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo_root)), check_puml_syntax=False,
                                  catalogs=_catalogs()),
        clear_repo_caches=lambda _path: None,
        artifact_id=artifact_id,
        diagram_entities={"lifeline": [{"id": "a", "label": "Renamed"}]},
        dry_run=True,
    )


def test_a_diagram_a_newer_product_wrote_is_refused_and_says_why(tmp_path: Path) -> None:
    artifact_id = _sequence_diagram(tmp_path, version=2)

    with pytest.raises(ValueError, match="format version 2, and this product writes version 1"):
        _edit(tmp_path, artifact_id)


def test_a_diagram_in_the_version_this_product_writes_is_edited(tmp_path: Path) -> None:
    artifact_id = _sequence_diagram(tmp_path, version=None)

    result = _edit(tmp_path, artifact_id)

    assert getattr(result, "content", None) is not None


def test_a_version_is_read_once_and_stamped_only_above_the_first() -> None:
    assert stated_format_version({}) == 1
    assert stated_format_version({"diagram-format-version": 3}) == 3
    assert stated_format_version({"diagram-format-version": True}) == 1
    assert version_to_stamp(1) is None and version_to_stamp(2) == 2
    assert newer_format_refusal({"diagram-format-version": 2}, 2, "datatype") is None


def test_each_type_declares_the_version_it_writes() -> None:
    from src.diagram_types.activity import module as activity  # noqa: PLC0415
    from src.diagram_types.datatype import module as datatype  # noqa: PLC0415
    from src.diagram_types.sequence import module as sequence  # noqa: PLC0415

    assert (activity.diagram_format_version, sequence.diagram_format_version, datatype.diagram_format_version) == (
        1, 1, 2,
    )
