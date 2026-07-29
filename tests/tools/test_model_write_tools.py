"""BDD scenarios for the MCP model writer tools.

These tests call the tool functions directly (without starting an MCP server)
so we can validate deterministic content generation and verifier-gated writes.

Updated for ArchiMate 4.0 conventions:
- model/ directory (not model-entities/)
- .outgoing.md connections (not connections/ directory)
- New ID format: TYPE@epoch.random.friendly-name
- Removed: phase_produced, owner_agent, produced_by_skill, engagement, safety-relevant
- Added: keywords, last-updated
- model_add_connection (not model_create_connection)
"""

from functools import lru_cache
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when

from src.application.modeling.artifact_write import generate_diagram_id, prefix_for_diagram_type
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as tools


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())

scenarios("features/model_write_tools.feature")


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    # Minimal architecture repo skeleton with new conventions.
    root = tmp_path / "engagements" / "ENG-TEST" / "work-repositories" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@given("an empty engagement architecture repository")
def empty_repo(repo_root: Path) -> Path:
    return repo_root


@when("I dry-run create an entity", target_fixture="dry_run_result")
def dry_run_create_entity(repo_root: Path) -> dict[str, object]:
    return tools.artifact_create_entity(
        artifact_type="capability",
        name="My Capability",
        summary="A short description.",
        dry_run=True,
        repo_root=str(repo_root),
    )


@then("the dry-run result should include a valid entity verification")
def dry_run_result_valid(dry_run_result: dict[str, object]) -> None:
    verification = dry_run_result["verification"]
    assert isinstance(verification, dict)
    assert verification["file_type"] == "entity"
    assert verification["valid"] is True


def test_dry_run_entity_template_empty_attrs_without_schema(repo_root: Path) -> None:
    result = tools.artifact_create_entity(
        artifact_type="capability",
        name="Capability With Scaffold",
        summary="A short description.",
        dry_run=True,
        repo_root=str(repo_root),
    )

    content = str(result["content"])

    # No attribute schema in this fixture repo → empty properties table
    assert "| (none) | (none) |" in content


def test_dry_run_entity_template_scaffold_from_schema(repo_root: Path) -> None:
    import json

    schema_dir = repo_root / ".arch-repo" / "schemata"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "type": "object",
        "required": ["Maturity"],
        "properties": {
            "Maturity": {"type": "string"},
            "Realizes": {"type": "string"},
        },
    }
    (schema_dir / "attributes.capability.schema.json").write_text(json.dumps(schema))

    result = tools.artifact_create_entity(
        artifact_type="capability",
        name="Capability With Scaffold",
        summary="A short description.",
        dry_run=True,
        repo_root=str(repo_root),
    )

    content = str(result["content"])

    assert "| Maturity | |" in content
    assert "| Realizes | |" in content


@when("I attempt to add a connection referencing unknown entities", target_fixture="conn_error")
def add_connection_unknown_entities(repo_root: Path) -> Exception:
    with pytest.raises(Exception) as exc:
        tools.artifact_add_connection(
            connection_type="archimate-serving",
            source_entity="APP@0000000000.XXXXXX.nonexistent-source",
            target_entity="APP@0000000000.YYYYYY.nonexistent-target",
            dry_run=False,
            repo_root=str(repo_root),
        )
    return exc.value


@then("the call should fail with a helpful error")
def connection_error_helpful(conn_error: Exception) -> None:
    msg = str(conn_error)
    assert "not found" in msg.lower() or "unknown" in msg.lower() or "cannot" in msg.lower()


def _write_entity(repo_root: Path, artifact_type: str, name: str) -> dict[str, object]:
    """Create an entity using the tool and return the result dict."""
    result = tools.artifact_create_entity(
        artifact_type=artifact_type,
        name=name,
        summary=f"Test entity: {name}",
        dry_run=False,
        repo_root=str(repo_root),
    )
    assert result.get("wrote") is True
    return result


@given(
    "an engagement architecture repository with two entities and one connection",
    target_fixture="repo_with_entities_and_connection",
)
def repo_with_entities_and_connection(repo_root: Path) -> tuple[Path, str, str]:
    e1 = _write_entity(repo_root, "application-component", "EventStore")
    e2 = _write_entity(repo_root, "application-component", "LangGraph Orchestrator")

    e1_id = str(e1["artifact_id"])
    e2_id = str(e2["artifact_id"])

    conn = tools.artifact_add_connection(
        connection_type="archimate-serving",
        source_entity=e1_id,
        target_entity=e2_id,
        dry_run=False,
        repo_root=str(repo_root),
    )
    assert conn.get("wrote") is True

    # Sanity: verifier should pass across repo.
    verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo_root)), catalogs=_catalogs())
    results = verifier.verify_all(repo_root)
    assert all(r.valid for r in results), [i for r in results for i in r.errors]
    return repo_root, e1_id, e2_id


@when("I create an archimate diagram with serving connection", target_fixture="diagram_result")
def create_archimate_diagram(
    repo_with_entities_and_connection: tuple[Path, str, str],
) -> dict[str, object]:
    repo_root, e1_id, e2_id = repo_with_entities_and_connection
    artifact_id = generate_diagram_id("archimate-application", "Test Diagram")

    # Derive aliases from entity IDs: TYPE_randompart
    e1_parts = e1_id.split(".")
    e2_parts = e2_id.split(".")
    e1_alias = f"{e1_parts[0].split('@')[0]}_{e1_parts[1]}"
    e2_alias = f"{e2_parts[0].split('@')[0]}_{e2_parts[1]}"

    puml = f"""@startuml {artifact_id}
!include ../_archimate-stereotypes.puml
!include ../_archimate-glyphs.puml

rectangle "Component A" <<application_component>> as {e1_alias}
rectangle "Component B" <<application_component>> as {e2_alias}

{e1_alias} --> {e2_alias} : <<serving>>
@enduml
"""
    return tools.artifact_create_diagram(
        diagram_type="archimate-application",
        name="Test Diagram",
        puml=puml,
        artifact_id=artifact_id,
        dry_run=False,
        repo_root=str(repo_root),
        connection_inference="strict",
    )


@then("the diagram should verify successfully and reference the inferred ids")
def diagram_inferred_ids(
    diagram_result: dict[str, object],
    repo_with_entities_and_connection: tuple[Path, str, str],
) -> None:
    assert diagram_result.get("wrote") is True

    repo_root, e1_id, e2_id = repo_with_entities_and_connection

    # Verify the created file.
    p = Path(diagram_result["path"])
    verifier = ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo_root)), catalogs=_catalogs())
    res = verifier.verify_diagram_file(p)
    assert res.valid is True, res.issues

    content = p.read_text(encoding="utf-8")
    assert "title Test Diagram" in content


def test_model_create_matrix_writes_valid_matrix(repo_root: Path) -> None:
    """Matrix creation should produce a verifiable matrix diagram file."""
    _write_entity(repo_root, "application-component", "EventStore")

    result = tools.artifact_create_matrix(
        name="Connection Matrix",
        matrix_markdown=("| Source | Target | Type |\n|---|---|---|\n| EventStore | Orchestrator | serving |\n"),
        artifact_id=generate_diagram_id("matrix", "Connection Matrix"),
        dry_run=False,
        repo_root=str(repo_root),
    )

    assert result.get("wrote") is True
    verification = result.get("verification")
    assert isinstance(verification, dict)
    assert verification.get("valid") is True


def test_diagram_prefixes_are_family_specific() -> None:
    assert prefix_for_diagram_type("archimate-business") == "ARC"
    assert prefix_for_diagram_type("matrix") == "MAT"
    assert prefix_for_diagram_type("sequence") == "SEQ"
    assert prefix_for_diagram_type("activity") == "ACT"
    assert prefix_for_diagram_type("er") == "ERD"
    assert generate_diagram_id("matrix", "Connection Matrix").startswith("MAT@")


def test_model_create_matrix_generates_typed_id_when_omitted(repo_root: Path) -> None:
    result = tools.artifact_create_matrix(
        name="Generated Matrix",
        matrix_markdown="| Source | Target | Type |\n|---|---|---|\n",
        artifact_id=None,
        dry_run=False,
        repo_root=str(repo_root),
    )

    assert result.get("wrote") is True
    artifact_id = str(result.get("artifact_id"))
    assert artifact_id.startswith("MAT@")
    assert artifact_id.endswith(".generated-matrix")
    assert Path(str(result["path"])).name == f"{artifact_id}.md"


def test_model_create_diagram_mints_canonical_id_for_bare_startuml_label(repo_root: Path) -> None:
    """A bare @startuml label must not leak into the artifact-id (W041); when no
    artifact_id is given, a canonical id is minted regardless of the puml label."""
    from src.application.verification.artifact_verifier_types import ENTITY_ID_RE

    puml = "@startuml the-forces-shaping-this-system\ntitle Forces\nrectangle X\n@enduml\n"
    result = tools.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="The Forces Shaping This System",
        puml=puml,
        artifact_id=None,
        dry_run=True,
        repo_root=str(repo_root),
        connection_inference="none",
    )

    artifact_id = str(result.get("artifact_id"))
    assert artifact_id != "the-forces-shaping-this-system"
    assert ENTITY_ID_RE.match(artifact_id), artifact_id
    assert artifact_id.startswith("ARC@")
    assert artifact_id.endswith(".the-forces-shaping-this-system")
    assert Path(str(result["path"])).name == f"{artifact_id}.puml"


def test_model_create_diagram_preserves_canonical_startuml_id(repo_root: Path) -> None:
    """A canonical id in @startuml (round-tripping a generated diagram) is kept."""
    canonical = "ARC@1777455142.cFB8Hs.the-forces-shaping-this-system"
    puml = f"@startuml {canonical}\ntitle Forces\nrectangle X\n@enduml\n"
    result = tools.artifact_create_diagram(
        diagram_type="archimate-motivation",
        name="The Forces Shaping This System",
        puml=puml,
        artifact_id=None,
        dry_run=True,
        repo_root=str(repo_root),
        connection_inference="none",
    )

    assert str(result.get("artifact_id")) == canonical


def test_model_create_diagram_dry_run_accepts_inlined_archimate_stereotypes(
    repo_root: Path,
) -> None:
    e1 = _write_entity(repo_root, "application-component", "EventStore")
    e2 = _write_entity(repo_root, "application-component", "LangGraph Orchestrator")
    e1_id = str(e1["artifact_id"])
    e2_id = str(e2["artifact_id"])
    conn = tools.artifact_add_connection(
        connection_type="archimate-serving",
        source_entity=e1_id,
        target_entity=e2_id,
        dry_run=False,
        repo_root=str(repo_root),
    )
    assert conn.get("wrote") is True

    e1_parts = e1_id.split(".")
    e2_parts = e2_id.split(".")
    e1_alias = f"{e1_parts[0].split('@')[0]}_{e1_parts[1]}"
    e2_alias = f"{e2_parts[0].split('@')[0]}_{e2_parts[1]}"

    puml = f"""@startuml inlined-archimate-save
!include ../_archimate-stereotypes.puml

title Test Diagram

rectangle "Left" <<application_component>> as {e1_alias}
rectangle "Right" <<application_component>> as {e2_alias}
Rel_Serving({e1_alias}, {e2_alias}, "")
@enduml
"""
    result = tools.artifact_create_diagram(
        diagram_type="archimate-application",
        name="Test Diagram",
        puml=puml,
        artifact_id=None,
        dry_run=True,
        repo_root=str(repo_root),
        connection_inference="none",
    )

    verification = result.get("verification")
    assert isinstance(verification, dict)
    assert verification.get("valid") is True, verification


def test_model_create_diagram_dry_run_infers_reference_ids_from_rel_macro(repo_root: Path) -> None:
    e1 = _write_entity(repo_root, "application-component", "Frontend")
    e2 = _write_entity(repo_root, "application-component", "Backend")
    e1_id = str(e1["artifact_id"])
    e2_id = str(e2["artifact_id"])
    conn = tools.artifact_add_connection(
        connection_type="archimate-serving",
        source_entity=e1_id,
        target_entity=e2_id,
        dry_run=False,
        repo_root=str(repo_root),
    )
    assert conn.get("wrote") is True

    e1_alias = f"{e1_id.split('.')[0].split('@')[0]}_{e1_id.split('.')[1]}"
    e2_alias = f"{e2_id.split('.')[0].split('@')[0]}_{e2_id.split('.')[1]}"
    puml = f"""@startuml inferred-rel-macro
!include ../_archimate-stereotypes.puml
!include ../_archimate-glyphs.puml

rectangle "Frontend" <<application_component>> as {e1_alias}
rectangle "Backend" <<application_component>> as {e2_alias}
Rel_Serving({e1_alias}, {e2_alias}, "HTTPS 443")
@enduml
"""

    result = tools.artifact_create_diagram(
        diagram_type="archimate-application",
        name="Inferred Rel Macro Diagram",
        puml=puml,
        artifact_id="ARC@1777000000.tstxx.inferred-rel-macro-diagram",
        dry_run=True,
        repo_root=str(repo_root),
    )

    content = str(result.get("content", ""))
    assert e1_id in content
    assert e2_id in content
    assert f"{stable_id(e1_id)}---{stable_id(e2_id)}@@archimate-serving" in content


def test_model_create_diagram_entity_ids_uses_renderer_and_connection_labels(repo_root: Path) -> None:
    e1 = _write_entity(repo_root, "application-component", "Frontend")
    e2 = _write_entity(repo_root, "application-component", "Backend")
    e1_id = str(e1["artifact_id"])
    e2_id = str(e2["artifact_id"])
    conn = tools.artifact_add_connection(
        connection_type="archimate-serving",
        source_entity=e1_id,
        target_entity=e2_id,
        description="HTTPS 443",
        dry_run=False,
        repo_root=str(repo_root),
    )
    assert conn.get("wrote") is True

    result = tools.artifact_create_diagram(
        diagram_type="archimate-application",
        name="Renderer-backed Diagram",
        entity_ids=[e1_id, e2_id],
        artifact_id="ARC@1777000000.tstxx.renderer-backed-diagram",
        dry_run=True,
        repo_root=str(repo_root),
        diagram_connections=[
            {
                "artifact_id": f"{e1_id}---{e2_id}@@archimate-serving",
                "include_description": True,
                "label": "TLS",
            }
        ],
    )

    verification = result.get("verification")
    assert isinstance(verification, dict)
    assert verification.get("valid") is True, verification
    content = str(result.get("content", ""))
    assert " --> " in content  # serving arrow style from ontology puml_arrow
    assert "HTTPS 443 | TLS" in content
    assert f"{e1_id}---{e2_id}@@archimate-serving" in content


def test_model_create_diagram_short_form_entity_ids_produce_non_empty_body(repo_root: Path) -> None:
    """Short-form IDs (PREFIX@epoch.random, no slug) must expand before lookup.

    Regression: passing short-form IDs caused get_entity() misses, producing an
    empty render body and an E303 ArchiMate stereotypes error.
    """
    e1 = _write_entity(repo_root, "application-component", "Alpha")
    e2 = _write_entity(repo_root, "application-component", "Beta")
    e1_full = str(e1["artifact_id"])
    e2_full = str(e2["artifact_id"])
    # Build short-form IDs: strip the slug suffix (everything from the second dot onward)
    parts1 = e1_full.split(".")
    parts2 = e2_full.split(".")
    e1_short = f"{parts1[0]}.{parts1[1]}"
    e2_short = f"{parts2[0]}.{parts2[1]}"
    assert e1_short != e1_full, "test requires the full ID to include a slug"

    tools.artifact_add_connection(
        connection_type="archimate-serving",
        source_entity=e1_full,
        target_entity=e2_full,
        dry_run=False,
        repo_root=str(repo_root),
    )

    result = tools.artifact_create_diagram(
        diagram_type="archimate-application",
        name="Short ID Diagram",
        entity_ids=[e1_short, e2_short],
        dry_run=True,
        repo_root=str(repo_root),
    )

    verification = result.get("verification")
    assert isinstance(verification, dict)
    assert verification.get("valid") is True, verification
    content = str(result.get("content", ""))
    # Both entities must appear in the rendered body
    assert "Alpha" in content
    assert "Beta" in content
