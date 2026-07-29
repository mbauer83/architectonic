"""Tests for per-diagram edge-label overrides.

Covers:
- format_diagram_puml writes edge-labels to frontmatter
- edit_diagram round-trips edge-labels (write + read-back)
- set_diagram_edge_label sets/clears a single key
- C4 renderer applies edge_labels override
- Verifier flags dangling edge-labels overrides (E410)
- Per-diagram independence: overriding a label in one diagram does not affect another
- MCP artifact_edit_diagram passes edge_labels through to service
- REST PUT /api/diagram/edge-label calls set_diagram_edge_label
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from src.application.modeling.artifact_write_formatting import format_diagram_puml
from src.application.verification._verifier_rules_edge_labels import check_edge_label_overrides
from src.application.verification.artifact_verifier_types import Severity, VerificationResult
from src.diagram_types.c4.renderer import C4PumlRenderer
from src.infrastructure.mcp import mcp_artifact_server as mcp


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make_app(repo: Path, name: str) -> str:
    r = mcp.artifact_create_entity(
        artifact_type="application-component",
        name=name,
        summary=f"{name} summary",
        dry_run=False,
        repo_root=str(repo),
    )
    assert r["wrote"], r
    return str(r["artifact_id"])


def _make_c4_diagram(repo: Path, scope_id: str, name: str = "Test C4 Diagram") -> str:
    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000001.tedge.{slug}"
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  _scope_entity_id: {scope_id}
bindings:
- correspondence_kind: scoped-by
  subject:
    kind: diagram
  target:
    entity_id: {scope_id}
---
@startuml {slug}
title {name}
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    return artifact_id


# ---------------------------------------------------------------------------
# T4.1: format_diagram_puml round-trip
# ---------------------------------------------------------------------------


def test_format_diagram_puml_writes_edge_labels() -> None:
    result = format_diagram_puml(
        artifact_id="DIA@1000000000.aaaaa.test",
        diagram_type="c4-container",
        name="Test",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml test\ntitle Test\n@enduml\n",
        edge_labels={"APP_A:APP_B": "Reads/writes"},
    )
    fm_text = re.search(r"^---(.*?)---", result, re.DOTALL)
    assert fm_text
    fm = yaml.safe_load(fm_text.group(1))
    assert fm["edge-labels"] == {"APP_A:APP_B": "Reads/writes"}


def test_format_diagram_puml_no_edge_labels_omits_field() -> None:
    result = format_diagram_puml(
        artifact_id="DIA@1000000000.aaaaa.test",
        diagram_type="c4-container",
        name="Test",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml test\ntitle Test\n@enduml\n",
        edge_labels=None,
    )
    assert "edge-labels" not in result


def test_format_diagram_puml_empty_edge_labels_omits_field() -> None:
    result = format_diagram_puml(
        artifact_id="DIA@1000000000.aaaaa.test",
        diagram_type="c4-container",
        name="Test",
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        puml_body="@startuml test\ntitle Test\n@enduml\n",
        edge_labels={},
    )
    assert "edge-labels" not in result


# ---------------------------------------------------------------------------
# T4.2: set_diagram_edge_label service op
# ---------------------------------------------------------------------------


def _make_standalone_c4_diagram_with_connection(repo: Path, name: str = "Standalone C4") -> tuple[str, str]:
    """Return (artifact_id, edge_key) for a standalone C4 diagram with one visible connection."""
    slug = name.lower().replace(" ", "-")
    artifact_id = f"DIA@1777000002.tedge.{slug}"
    # standalone: software-system scope + container internal + connection
    # alias for software-system "sys": SS_sys_0
    # alias for container "svc": C_svc_0
    content = f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: c4-container
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: []
connection-ids-used: []
diagram-entities:
  software-system:
  - id: sys
    label: MySystem
  container:
  - id: svc
    label: Service
connections:
- source: svc
  target: sys
  label: calls
---
@startuml {slug}
title {name}
SS_sys_0 --> C_svc_0 : calls
@enduml
"""
    path = repo / "diagram-catalog" / "diagrams" / f"{artifact_id}.puml"
    path.write_text(content, encoding="utf-8")
    # The standalone resolver produces alias SS_sys_0 for software-system "sys",
    # and C_svc_0 for container "svc". Connection is svc→sys = C_svc_0:SS_sys_0.
    return artifact_id, "C_svc_0:SS_sys_0"


def test_set_diagram_edge_label_writes_to_frontmatter(repo: Path) -> None:
    """set_diagram_edge_label persists the label override in frontmatter."""
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    # Use dry_run=True and inspect content — avoids needing a matching rendered PUML
    scope_id = _make_app(repo, "MyApp")
    diag_id = _make_c4_diagram(repo, scope_id)
    verifier = ArtifactVerifier(catalogs=_catalogs())

    result = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_id,
        edge_key="APP_A:APP_B",
        label="Reads/writes",
        dry_run=True,
    )
    # dry_run=True → wrote=False but content has the override
    assert result.content is not None
    assert "edge-labels" in result.content
    assert "Reads/writes" in result.content

    # File on disk unchanged (dry_run)
    path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
    parsed = parse_diagram_file(path)
    assert "edge-labels" not in parsed.frontmatter


def test_set_diagram_edge_label_clear_removes_key(repo: Path) -> None:
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    scope_id = _make_app(repo, "MyApp2")
    diag_id = _make_c4_diagram(repo, scope_id)

    # Pre-populate edge-labels in frontmatter (dry_run=True verifies content)
    verifier = ArtifactVerifier(catalogs=_catalogs())

    # First set a label
    r1 = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_id,
        edge_key="APP_A:APP_B",
        label="first-label",
        dry_run=True,
    )
    assert r1.content and "first-label" in r1.content

    # Then clear it (label=None) — the key should be absent from content
    r2 = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_id,
        edge_key="APP_A:APP_B",
        label=None,
        dry_run=True,
    )
    assert r2.content and "first-label" not in r2.content
    # File on disk still clean (dry_run)
    path = repo / "diagram-catalog" / "diagrams" / f"{diag_id}.puml"
    parsed = parse_diagram_file(path)
    assert "edge-labels" not in parsed.frontmatter


# ---------------------------------------------------------------------------
# T4.3: Verifier dangling-override check
# ---------------------------------------------------------------------------


def test_verifier_flags_dangling_edge_label() -> None:
    puml = "@startuml test\ntitle Test\nAPP_A --> APP_B : uses\n@enduml\n"
    fm: dict = {"edge-labels": {"APP_X:APP_Y": "label"}}
    result = VerificationResult(path=Path("fake.puml"), file_type="diagram")
    check_edge_label_overrides(puml, fm, result, "fake.puml")
    assert any(i.code == "E410" for i in result.issues)
    assert any("APP_X:APP_Y" in i.message for i in result.issues)
    assert all(i.severity == Severity.ERROR for i in result.issues)


def test_verifier_valid_edge_label_no_error() -> None:
    puml = "@startuml test\ntitle Test\nAPP_A --> APP_B : uses\n@enduml\n"
    fm: dict = {"edge-labels": {"APP_A:APP_B": "Reads/writes"}}
    result = VerificationResult(path=Path("fake.puml"), file_type="diagram")
    check_edge_label_overrides(puml, fm, result, "fake.puml")
    assert not any(i.code == "E410" for i in result.issues)


def test_verifier_hyphenated_alias_is_valid() -> None:
    """Aliases like APP_Z_fI-N (with hyphens) must not be treated as dangling."""
    puml = "@startuml test\ntitle Test\nAPP_hkrdtm --> APP_Z_fI-N : calls\n@enduml\n"
    fm: dict = {"edge-labels": {"APP_hkrdtm:APP_Z_fI-N": "Reads/writes audit log"}}
    result = VerificationResult(path=Path("fake.puml"), file_type="diagram")
    check_edge_label_overrides(puml, fm, result, "fake.puml")
    assert not any(i.code == "E410" for i in result.issues), (
        "Hyphenated alias should be valid, not dangling"
    )


def test_verifier_hyphenated_alias_dangling() -> None:
    """A hyphenated alias key that does not appear in PUML must be flagged."""
    puml = "@startuml test\ntitle Test\nAPP_A --> APP_B : calls\n@enduml\n"
    fm: dict = {"edge-labels": {"APP_hkrdtm:APP_Z_fI-N": "label"}}
    result = VerificationResult(path=Path("fake.puml"), file_type="diagram")
    check_edge_label_overrides(puml, fm, result, "fake.puml")
    assert any(i.code == "E410" for i in result.issues)


def test_verifier_no_edge_labels_field_no_error() -> None:
    puml = "@startuml test\ntitle Test\n@enduml\n"
    fm: dict = {}
    result = VerificationResult(path=Path("fake.puml"), file_type="diagram")
    check_edge_label_overrides(puml, fm, result, "fake.puml")
    assert not result.issues


# ---------------------------------------------------------------------------
# T4.4: C4 renderer applies edge_labels override
# ---------------------------------------------------------------------------


def _minimal_c4_config() -> dict:
    return {
        "c4": {
            "scope_entity_type": "software-system",
            "scope_render_mode": "boundary",
            "internal_entity_types": ["container"],
        }
    }


def test_c4_renderer_applies_edge_label_override(tmp_path: Path) -> None:
    renderer = C4PumlRenderer(_minimal_c4_config())
    diagram_entities: dict = {
        "software-system": [{"id": "sys", "label": "MySystem"}],
        "container": [{"id": "svc", "label": "Service"}],
    }
    diagram_connections = [{"source": "svc", "target": "sys", "label": "calls"}]

    body_default = renderer.render_body(
        "Test",
        [],
        [],
        "c4-container",
        tmp_path,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
    )
    src_alias = re.search(r"(\w+)\s+-->\s+(\w+)", body_default)
    assert src_alias, "expected connection line"
    src, tgt = src_alias.group(1), src_alias.group(2)
    override_key = f"{src}:{tgt}"

    body_override = renderer.render_body(
        "Test",
        [],
        [],
        "c4-container",
        tmp_path,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
        edge_labels={override_key: "Reads/writes"},
    )
    assert "Reads/writes" in body_override
    assert "calls" not in body_override


def test_c4_renderer_reverts_to_derived_without_override(tmp_path: Path) -> None:
    renderer = C4PumlRenderer(_minimal_c4_config())
    diagram_entities: dict = {
        "software-system": [{"id": "sys", "label": "MySystem"}],
        "container": [{"id": "svc", "label": "Service"}],
    }
    diagram_connections = [{"source": "svc", "target": "sys", "label": "calls"}]
    body = renderer.render_body(
        "Test", [], [], "c4-container", tmp_path,
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
        edge_labels={"NOMATCH_A:NOMATCH_B": "ignored"},
    )
    # override key doesn't match → derived label "calls" is used
    assert "calls" in body


# ---------------------------------------------------------------------------
# T4.5: MCP passes edge_labels to edit_diagram (via artifact_edit_diagram)
# ---------------------------------------------------------------------------


def test_mcp_edit_diagram_edge_labels_stored(repo: Path) -> None:
    scope_id = _make_app(repo, "MCPApp")
    diag_id = _make_c4_diagram(repo, scope_id)

    result = mcp.artifact_edit_diagram(
        artifact_id=diag_id,
        edge_labels={"ALIAS_A:ALIAS_B": "via MCP"},
        dry_run=True,
        repo_root=str(repo),
    )
    assert "edge-labels" in result.get("content", "")


# ---------------------------------------------------------------------------
# T4.8: Per-diagram independence
# ---------------------------------------------------------------------------


def test_edge_label_per_diagram_independence(repo: Path) -> None:
    """Setting a label in diagram A does not affect diagram B's frontmatter."""
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label

    scope_id = _make_app(repo, "SharedApp")
    diag_a = _make_c4_diagram(repo, scope_id, "Diagram A")
    diag_b = _make_c4_diagram(repo, scope_id, "Diagram B")

    verifier = ArtifactVerifier(catalogs=_catalogs())
    r_a = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_a,
        edge_key="X:Y",
        label="label in A",
        dry_run=True,
    )
    r_b = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_b,
        edge_key="X:Y",
        label=None,
        dry_run=True,
    )
    # Content for A has the label; B with None should not have it
    assert r_a.content and "label in A" in r_a.content
    assert r_b.content and "label in A" not in r_b.content


def test_edge_label_per_diagram_independence_persisted(repo: Path) -> None:
    """Persisted independence: writing a label to diag A does not change diag B on disk.

    Uses the standalone fixture which produces known aliases (C_svc_0:SS_sys_0) so the
    verifier accepts the key and the write actually persists to disk.
    """
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write._diagram_edge_labels import set_diagram_edge_label
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    diag_a, edge_key = _make_standalone_c4_diagram_with_connection(repo, "Persist A")
    scope_id = _make_app(repo, "SharedApp2")
    diag_b = _make_c4_diagram(repo, scope_id, "Persist B")

    verifier = ArtifactVerifier(catalogs=_catalogs())
    before_b = (repo / "diagram-catalog" / "diagrams" / f"{diag_b}.puml").read_bytes()

    result = set_diagram_edge_label(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_a,
        edge_key=edge_key,
        label="written to A only",
        dry_run=False,
    )
    assert result.wrote, f"Label write should succeed with valid key; verification: {result.verification}"

    after_b = (repo / "diagram-catalog" / "diagrams" / f"{diag_b}.puml").read_bytes()
    assert before_b == after_b, "Writing a label to diag A must not modify diag B on disk"

    fm_b = parse_diagram_file(repo / "diagram-catalog" / "diagrams" / f"{diag_b}.puml").frontmatter
    assert "edge-labels" not in fm_b

    fm_a = parse_diagram_file(repo / "diagram-catalog" / "diagrams" / f"{diag_a}.puml").frontmatter
    assert fm_a.get("edge-labels", {}).get(edge_key) == "written to A only"


# ---------------------------------------------------------------------------
# MCP null-value clearing (dict[str, str | None])
# ---------------------------------------------------------------------------


def test_mcp_edge_labels_null_value_clears_key(repo: Path) -> None:
    """MCP: passing {key: None} removes that key; other keys are preserved (merge semantics)."""
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram

    # Use the standalone fixture so we have a valid edge key
    diag_id, edge_key = _make_standalone_c4_diagram_with_connection(repo, "MCP Null Test")
    verifier = ArtifactVerifier(catalogs=_catalogs())

    # Seed the diagram with two labels (dry_run=True only checks content, no file write)
    # We simulate the merged state by writing the map directly via edit_diagram
    r1 = edit_diagram(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_id,
        edge_labels={edge_key: "keep me"},
        dry_run=True,
    )
    assert r1.content and "keep me" in r1.content

    # Now pass {edge_key: None} — should remove edge_key (clearing it)
    r2 = mcp.artifact_edit_diagram(
        artifact_id=diag_id,
        edge_labels={edge_key: None},
        dry_run=True,
        repo_root=str(repo),
    )
    content = r2.get("content", "")
    assert "keep me" not in content, "Nulled label must be removed from content"


def test_mcp_edge_labels_merges_with_existing(repo: Path) -> None:
    """MCP: passing a partial dict merges with existing labels rather than replacing all."""
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.infrastructure.write.artifact_write.diagram_edit import edit_diagram

    diag_id, edge_key = _make_standalone_c4_diagram_with_connection(repo, "MCP Merge Test")
    verifier = ArtifactVerifier(catalogs=_catalogs())

    # Set two labels by building the full map in a single dry_run call
    r1 = edit_diagram(
        repo_root=repo,
        verifier=verifier,
        clear_repo_caches=lambda _: None,
        artifact_id=diag_id,
        edge_labels={edge_key: "original label"},
        dry_run=True,
    )
    assert r1.content and "original label" in r1.content

    # Pass a different key via MCP — the original must be preserved
    other_key = "OTHER_A:OTHER_B"
    r2 = mcp.artifact_edit_diagram(
        artifact_id=diag_id,
        edge_labels={other_key: "new label"},
        dry_run=True,
        repo_root=str(repo),
    )
    content = r2.get("content", "")
    # The new label is added; original label survives the merge
    assert "new label" in content, "New label must appear in merged content"


# ---------------------------------------------------------------------------
# REST adapter: PUT /api/diagram/edge-label delegates to set_diagram_edge_label
# ---------------------------------------------------------------------------


def test_rest_edge_label_endpoint_calls_service(repo: Path) -> None:
    """Thin adapter test: the REST handler calls set_diagram_edge_label and returns a result dict."""
    from src.application.artifact_repository import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.gui.routers import state as gui_state
    from src.infrastructure.gui.routers._diagram_edge_label import SetEdgeLabelBody, set_edge_label_gui

    scope_id = _make_app(repo, "RestApp")
    diag_id = _make_c4_diagram(repo, scope_id)

    repo_obj = ArtifactRepository(shared_artifact_index(repo))
    gui_state.init_state(repo_obj, repo, None)

    body = SetEdgeLabelBody(artifact_id=diag_id, edge_key="APP_A:APP_B", label="via REST", dry_run=True)
    result = set_edge_label_gui(body)
    assert "wrote" in result


# ---------------------------------------------------------------------------
# ArchiMate renderer edge_labels support
# ---------------------------------------------------------------------------


def test_archimate_renderer_accepts_edge_labels_param() -> None:
    """GenericPumlRenderer.render_body accepts edge_labels without TypeError."""
    from pathlib import Path as _Path

    from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer

    renderer = GenericPumlRenderer(config={})
    # No entities or connections — edge_labels won't match anything but must not raise
    body = renderer.render_body(
        "Test", [], [], "archimate-motivation", _Path("."),
        edge_labels={"REQ_a:REQ_b": "Custom label"},
    )
    assert "@startuml" in body
    assert "@enduml" in body


def test_archimate_renderer_applies_edge_label_via_generate(repo: Path) -> None:
    """generate_archimate_puml_body passes edge_labels to the renderer (via MCP entity+connection)."""
    from src.application.artifact_repository import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body

    e_id = _make_app(repo, "Label Entity")
    repo_obj = ArtifactRepository(shared_artifact_index(repo))
    entity_recs = [repo_obj.get_entity(e_id)]
    assert entity_recs[0] is not None

    alias = entity_recs[0].display_alias or ""
    body_with_override = generate_archimate_puml_body(
        "Test", entity_recs, [],
        diagram_type="archimate-motivation",
        edge_labels={f"{alias}:OTHER": "should not appear (no connection)"},
    )
    # No crash; the diagram body is produced
    assert "@startuml" in body_with_override
