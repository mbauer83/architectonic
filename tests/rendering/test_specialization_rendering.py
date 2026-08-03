"""Renderer snapshot tests: guillemet stereotype rendering for entities and
connections carrying a specialization, notation icon/color/line-style/label-marker overrides
when declared (parent-notation fallback otherwise), and composition with the existing
connection-type `show_stereotype` heuristic."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    SpecializationInfo,
    SpecializationNotation,
)
from src.infrastructure.rendering.archimate_entity_declarations import ICON_SCALE, entity_declaration
from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer


def _real_registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()

_ARCHIMATE_CONFIG = {
    "includes": [],
    "grouping": {"stereotype_pattern": "{hierarchy_0|capitalize}Grouping"},
    "layout": {"nesting_connection_classes": ["nesting"], "flow_connection_classes": ["flow"]},
}


def _entity(
    artifact_id: str, artifact_type: str, name: str, alias: str, *,
    specializations: tuple[str, ...] = (),
) -> EntityRecord:
    display_blocks = {"archimate": f'```yaml\nlabel: "{name}"\nalias: {alias}\n```'}
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain="business",
        subdomain=artifact_type,
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks=display_blocks,
        display_label=name,
        display_alias=alias,
        specializations=specializations,
    )


def _conn(
    source: str, target: str, conn_type: str, *, specializations: tuple[str, ...] = ()
) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"{source}---{target}@@{conn_type}",
        source=source,
        target=target,
        conn_type=conn_type,
        version="0.1.0",
        status="draft",
        path=Path("/tmp/test.outgoing.md"),
        extra={},
        content_text="",
        specializations=specializations,
    )


def _synthetic_catalog() -> SpecializationCatalog:
    return SpecializationCatalog(
        (
            SpecializationInfo(
                slug="iconic-collaboration",
                name="Iconic Collaboration",
                concept_kind="entity",
                parent_type="collaboration",
                module_alias="archimate-4",
                notation=SpecializationNotation(icon="custom_icon", color="lightblue"),
            ),
            SpecializationInfo(
                slug="styled-flow",
                name="Styled Flow",
                concept_kind="connection",
                parent_type="archimate-flow",
                module_alias="archimate-4",
                notation=SpecializationNotation(line_style="dashed", label_marker="$"),
            ),
        )
    )


def _patch_catalog(monkeypatch: pytest.MonkeyPatch, catalog: SpecializationCatalog) -> None:
    monkeypatch.setattr(GenericPumlRenderer, "_specialization_catalog", lambda self: catalog)


class TestEntityRendering:
    def test_specialization_guillemet_renders_via_real_catalog(self, tmp_path: Path) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        team = _entity(
            "COL@1.a.team", "collaboration", "Cross-team", "COL_TEAM", specializations=("business-collaboration",)
        )

        puml = renderer.render_body("Team", [team], [], "archimate-business", tmp_path)

        assert '«Business Collaboration»' in puml
        # On its own line: the guillemets qualify the element, they are not part of its name,
        # and running them together widened every node to the sum of both.
        assert 'rectangle "Cross-team\\n«Business Collaboration»" <<collaboration>> as COL_TEAM' in puml

    def test_specialization_icon_and_color_override_parent_notation(self) -> None:
        team = _entity(
            "COL@1.a.team", "collaboration", "Cross-team", "COL_TEAM", specializations=("iconic-collaboration",)
        )

        line = entity_declaration(team, "COL_TEAM", _real_registry(), frozenset(), _synthetic_catalog())

        assert f"<$archimate_custom_icon{{scale={ICON_SCALE}}}>" in line
        assert "#lightblue" in line
        assert "«Iconic Collaboration»" in line

    def test_no_specialization_is_unaffected(self, tmp_path: Path) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        team = _entity("COL@1.a.team", "collaboration", "Cross-team", "COL_TEAM")

        puml = renderer.render_body("Team", [team], [], "archimate-business", tmp_path)

        assert "«" not in puml
        assert 'rectangle "Cross-team" <<collaboration>> as COL_TEAM' in puml

    def test_multiple_specializations_render_as_a_comma_separated_list(self, tmp_path: Path) -> None:
        # ArchiMate §15.2: several specialization profiles show as one guillemet list.
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        team = _entity(
            "COL@1.a.team", "collaboration", "Cross-team", "COL_TEAM",
            specializations=("business-collaboration", "application-collaboration"),
        )

        puml = renderer.render_body("Team", [team], [], "archimate-business", tmp_path)

        assert "«Business Collaboration, Application Collaboration»" in puml


class TestConnectionRendering:
    def test_guillemet_renders_when_type_stereotype_is_suppressed(self, tmp_path: Path) -> None:
        # archimate-assignment declares puml_arrow and no explicit show_stereotype override,
        # so its type stereotype is suppressed by the existing heuristic — the specialization
        # guillemet must still render.
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(
            src.artifact_id, tgt.artifact_id, "archimate-assignment", specializations=("responsibility-assignment",)
        )

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "«Responsibility Assignment»" in puml
        assert "<<assignment>>" not in puml

    def test_multiple_connection_specializations_render_as_a_list(self, tmp_path: Path) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(
            src.artifact_id, tgt.artifact_id, "archimate-assignment",
            specializations=("responsibility-assignment", "behavior-assignment"),
        )

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "«Responsibility Assignment, Behavior Assignment»" in puml

    def test_guillemet_composes_with_shown_type_stereotype(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        monkeypatch.setattr(
            GenericPumlRenderer,
            "_connection_info",
            lambda self, conn_type: ConnectionTypeInfo(
                artifact_type=conn_type, conn_lang="Flow", puml_arrow="-->", show_stereotype=True
            ),
        )
        _patch_catalog(monkeypatch, _synthetic_catalog())
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(src.artifact_id, tgt.artifact_id, "archimate-flow", specializations=("styled-flow",))

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "<<flow>>" in puml
        assert "«Styled Flow»" in puml

    def test_label_marker_prefixes_the_visible_label(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        monkeypatch.setattr(
            GenericPumlRenderer,
            "_connection_info",
            lambda self, conn_type: ConnectionTypeInfo(
                artifact_type=conn_type, conn_lang="Flow", puml_arrow="-->", show_stereotype=False
            ),
        )
        _patch_catalog(monkeypatch, _synthetic_catalog())
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(
            src.artifact_id, tgt.artifact_id, "archimate-flow",
            specializations=("styled-flow",),
        )

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "$ «Styled Flow»" in puml

    def test_line_style_applies_to_the_arrow(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        monkeypatch.setattr(
            GenericPumlRenderer,
            "_connection_info",
            lambda self, conn_type: ConnectionTypeInfo(
                artifact_type=conn_type, conn_lang="Flow", puml_arrow="-->", show_stereotype=False
            ),
        )
        _patch_catalog(monkeypatch, _synthetic_catalog())
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(src.artifact_id, tgt.artifact_id, "archimate-flow", specializations=("styled-flow",))

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "-[dashed]" in puml

    def test_no_specialization_is_unaffected(self, tmp_path: Path) -> None:
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        src = _entity("GRP@1.a.src", "grouping", "Src", "GRP_SRC")
        tgt = _entity("REQ@1.a.tgt", "requirement", "Tgt", "REQ_TGT")
        conn = _conn(src.artifact_id, tgt.artifact_id, "archimate-assignment")

        puml = renderer.render_body("Diag", [src, tgt], [conn], "archimate-motivation", tmp_path)

        assert "«" not in puml
