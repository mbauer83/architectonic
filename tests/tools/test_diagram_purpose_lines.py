"""A diagram says who it is for and what it answers: the write path takes the lists, the verifier holds their
references, and a viewpoint applied to a diagram type it does not declare itself for is reported (W183).

Against a fixture repository this file builds, so exact contents are the test's own.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification._verifier_rules_viewpoint import check_viewpoint_suits_diagram_type
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.purpose_lines import MalformedPurposeLine, Prose, Reference, read_purpose_lines
from src.domain.repository.frontmatter import parse_frontmatter
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.diagram import create_diagram
from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram
from src.infrastructure.write.artifact_write.types import WriteResult

STAKEHOLDER = "STK@1700000001.StkOps.operations"
GOAL = "GOL@1700000002.GolFst.fast-fulfilment"
COMPONENT = "APP@1700000003.AppOrd.order-service"
_BODY = '@startuml\nrectangle "Note" <<goal>> as N\n@enduml\n'


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write_entity(root: Path, artifact_id: str, artifact_type: str, domain: str, name: str) -> None:
    path = root / "model" / domain / artifact_type / f"{artifact_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nartifact-id: {artifact_id}\nartifact-type: {artifact_type}\nname: {name}\nversion: 0.1.0\n"
        f"status: draft\nlast-updated: '2026-01-01'\n---\n\n<!-- §content -->\n\n## {name}\n\nFixture.\n",
        encoding="utf-8",
    )


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write_entity(root, STAKEHOLDER, "stakeholder", "motivation", "Operations")
    _write_entity(root, GOAL, "goal", "motivation", "Fast fulfilment")
    _write_entity(root, COMPONENT, "application-component", "application", "Order service")
    return root


def _verifier(repo_root: Path) -> ArtifactVerifier:
    return build_artifact_verifier(
        ArtifactRegistry(shared_artifact_index(repo_root)), check_puml_syntax=False, catalogs=_catalogs(),
    )


def _create(repo_root: Path, *, dry_run: bool = False, **stated: object) -> WriteResult:
    return create_diagram(
        repo_root=repo_root, verifier=_verifier(repo_root), clear_repo_caches=lambda _path: None,
        diagram_type="archimate-motivation", name="Purpose", puml=_BODY,
        artifact_id="ARC@1700000009.DgmPur.purpose", version="0.1.0", status="draft", last_updated=None,
        dry_run=dry_run, **stated,  # type: ignore[arg-type]
    )


def _codes(result: WriteResult) -> set[str]:
    return {str(issue["code"]) for issue in result.verification.get("issues", [])}  # type: ignore[union-attr]


def _stored(result: WriteResult) -> dict[str, object]:
    return parse_frontmatter(result.path.read_text(encoding="utf-8"))


@pytest.mark.verifies("REQ@1795776616.Wl0K4oN")
def test_a_diagram_is_created_with_who_it_is_for_and_what_it_answers(repo_root: Path) -> None:
    result = _create(
        repo_root, stakeholders=["Warehouse staff", {"ref": STAKEHOLDER}], concerns=[{"ref": GOAL}, "How fast?"],
    )

    assert result.wrote, result.verification
    lines = read_purpose_lines(_stored(result))
    assert lines.stakeholders == (Prose("Warehouse staff"), Reference(STAKEHOLDER))
    assert lines.concerns == (Reference(GOAL), Prose("How fast?"))


def test_a_diagram_written_without_them_stays_valid_and_states_none(repo_root: Path) -> None:
    result = _create(repo_root)

    assert result.wrote, result.verification
    assert "stakeholders" not in _stored(result) and "concerns" not in _stored(result)


@pytest.mark.parametrize(
    ("stated", "code"),
    [
        ({"stakeholders": [{"ref": "STK@1799999999.Nobody.gone"}]}, "E186"),
        ({"concerns": [{"ref": "GOL@1799999999.Nobody.gone"}]}, "E186"),
        ({"stakeholders": [{"ref": GOAL}]}, "E187"),
        ({"concerns": [{"ref": COMPONENT}]}, "E187"),
    ],
)
@pytest.mark.verifies("REQ@1795776616.Wl0K4oN")
def test_a_reference_to_a_missing_or_unsuitable_element_is_refused_with_its_code(
    repo_root: Path, stated: dict[str, object], code: str
) -> None:
    result = _create(repo_root, **stated)

    assert not result.wrote
    assert code in _codes(result)
    assert not result.path.exists(), "a refused create leaves no file behind"


def test_a_dry_run_reports_the_refusal_too(repo_root: Path) -> None:
    assert "E187" in _codes(_create(repo_root, dry_run=True, concerns=[{"ref": COMPONENT}]))


def test_a_list_that_is_not_one_is_refused_before_anything_is_written(repo_root: Path) -> None:
    with pytest.raises(MalformedPurposeLine):
        _create(repo_root, stakeholders=[{"name": STAKEHOLDER}])


def _edit(repo_root: Path, **stated: object) -> WriteResult:
    return edit_diagram(
        assert_write_root=assert_engagement_write_root, repo_root=repo_root, verifier=_verifier(repo_root),
        clear_repo_caches=lambda _path: None, artifact_id="ARC@1700000009.DgmPur.purpose", dry_run=False,
        **stated,  # type: ignore[arg-type]
    )


def test_an_edit_keeps_a_list_it_omits_and_clears_one_given_empty(repo_root: Path) -> None:
    _create(repo_root, stakeholders=[{"ref": STAKEHOLDER}], concerns=["How fast?"])

    kept = _edit(repo_root, status="active")
    assert read_purpose_lines(_stored(kept)).stakeholders == (Reference(STAKEHOLDER),)

    replaced = _edit(repo_root, concerns=[{"ref": GOAL}])
    assert read_purpose_lines(_stored(replaced)).concerns == (Reference(GOAL),)
    assert read_purpose_lines(_stored(replaced)).stakeholders == (Reference(STAKEHOLDER),)

    cleared = _edit(repo_root, stakeholders=[])
    assert "stakeholders" not in _stored(cleared)


def test_an_edit_naming_an_unsuitable_element_is_refused_and_the_file_kept(repo_root: Path) -> None:
    created = _create(repo_root, concerns=["How fast?"])
    before = created.path.read_text(encoding="utf-8")

    refused = _edit(repo_root, stakeholders=[{"ref": COMPONENT}])

    assert not refused.wrote and "E187" in _codes(refused)
    assert created.path.read_text(encoding="utf-8") == before


def _warnings(result: WriteResult) -> list[dict[str, object]]:
    return [i for i in result.verification.get("issues", []) if i["code"] == "W183"]  # type: ignore[union-attr]


def test_a_viewpoint_meant_for_another_diagram_type_is_applied_and_reported(repo_root: Path) -> None:
    """`organization` declares itself for business diagrams; this one is a motivation diagram."""
    result = _create(repo_root, viewpoint={"slug": "organization", "version": 1})

    assert result.wrote, "a warning, not a refusal: the apply proceeds"
    [warning] = _warnings(result)
    message = str(warning["message"])
    assert "organization" in message and "archimate-motivation" in message and "archimate-business" in message


def test_a_viewpoint_meant_for_this_diagram_type_is_not_reported(repo_root: Path) -> None:
    assert not _warnings(_create(repo_root, viewpoint={"slug": "motivation", "version": 1}))


def _suitability(definition: ViewpointDefinition, diagram_type: str) -> set[str]:
    result = VerificationResult(path=Path("d.puml"), file_type="diagram")
    check_viewpoint_suits_diagram_type(
        {"viewpoint": {"slug": definition.slug, "version": 1}}, diagram_type,
        catalog=ViewpointCatalog((definition,)), result=result, loc="d.puml",
    )
    return {issue.code for issue in result.issues}


def test_a_viewpoint_declaring_no_diagram_types_suits_any() -> None:
    unrestricted = ViewpointDefinition(slug="anything", version=1, name="Anything")

    assert _suitability(unrestricted, "archimate-motivation") == set()
    assert _suitability(unrestricted, "c4-container") == set()


def test_a_declaring_viewpoint_warns_only_outside_its_types() -> None:
    declared = ViewpointDefinition(slug="biz", version=1, name="Biz", representation_types=("archimate-business",))

    assert _suitability(declared, "archimate-business") == set()
    assert _suitability(declared, "archimate-motivation") == {"W183"}
