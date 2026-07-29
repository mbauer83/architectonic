from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering.archimate_puml_renderer import ArchimatePumlRenderer
from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer

_ARCHIMATE_CONFIG = {
    "includes": [],   # was: ["_macros.puml"]
    "grouping": {"stereotype_pattern": "{hierarchy_0|capitalize}Grouping"},
    "layout": {
        "nesting_connection_classes": ["nesting"],
        "flow_connection_classes": ["flow"],
    },
}


def _entity(
    artifact_id: str,
    artifact_type: str,
    name: str,
    alias: str,
    *,
    domain: str = "motivation",
    subdomain: str = "goals",
    extra: dict[str, object] | None = None,
) -> EntityRecord:
    display_blocks = {"archimate": f'```yaml\nlabel: "{name}"\nalias: {alias}\n```'}
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain=domain,
        subdomain=subdomain,
        path=Path(f"/tmp/{artifact_id}.md"),
        keywords=(),
        extra=extra or {},
        content_text="",
        display_blocks=display_blocks,
        display_label=name,
        display_alias=alias,
    )


def _conn(
    source: str,
    target: str,
    conn_type: str = "archimate-realization",
    *,
    content_text: str = "",
    src_multiplicity: str = "",
    tgt_multiplicity: str = "",
    attributes: dict[str, object] | None = None,
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
        content_text=content_text,
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
        attributes=attributes or {},
    )


def test_render_body_uses_includes_and_single_domain_type_groupings(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    driver = _entity("DRV@1.a.driver-a", "driver", "Driver A", "DRV_A", subdomain="drivers")
    assessment = _entity("ASS@1.a.assessment-a", "assessment", "Assessment A", "ASS_A", subdomain="assessments")

    puml = renderer.render_body(
        "Drivers and Assessments",
        [driver, assessment],
        [_conn(driver.artifact_id, assessment.artifact_id, "archimate-influence")],
        "archimate-motivation",
        tmp_path,
    )

    assert "!include ../_macros.puml" not in puml
    # Connected elements group by their connection component, never by element type —
    # a type box would assert nothing the model holds.
    assert "<<MotivationGrouping>>" not in puml
    assert "top to bottom direction" in puml
    # Connected units carry the rank on the hinted arrow itself — a redundant hidden
    # anchor between them is exactly the construct that crashes GraphViz on some shapes.
    assert "DRV_A -[hidden]down- ASS_A" not in puml
    assert "DRV_A .down.> ASS_A" in puml


def test_render_body_boxes_only_connectionless_elements_by_type(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    driver = _entity("DRV@1.a.driver-a", "driver", "Driver A", "DRV_A", subdomain="drivers")
    assessment = _entity("ASS@1.a.assessment-a", "assessment", "Assessment A", "ASS_A", subdomain="assessments")
    loose_b = _entity("DRV@1.b.driver-b", "driver", "Driver B", "DRV_B", subdomain="drivers")
    loose_c = _entity("DRV@1.c.driver-c", "driver", "Driver C", "DRV_C", subdomain="drivers")

    puml = renderer.render_body(
        "Drivers and Assessments",
        [driver, assessment, loose_b, loose_c],
        [_conn(driver.artifact_id, assessment.artifact_id, "archimate-influence")],
        "archimate-motivation",
        tmp_path,
    )

    # The connectionless BAG gets the type-box fallback; the connected pair does not.
    assert 'rectangle "Drivers" <<MotivationGrouping>> as GRPT_' in puml
    box_start = puml.index('rectangle "Drivers"')
    box_end = puml.index("\n}", box_start)
    assert "DRV_B" in puml[box_start:box_end]
    assert "DRV_C" in puml[box_start:box_end]
    assert "DRV_A" not in puml[box_start:box_end]


def test_render_body_leaves_a_single_isolate_unboxed(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    driver = _entity("DRV@1.a.driver-a", "driver", "Driver A", "DRV_A", subdomain="drivers")
    assessment = _entity("ASS@1.a.assessment-a", "assessment", "Assessment A", "ASS_A", subdomain="assessments")
    loose = _entity("DRV@1.b.driver-b", "driver", "Driver B", "DRV_B", subdomain="drivers")

    puml = renderer.render_body(
        "Drivers and Assessments",
        [driver, assessment, loose],
        [_conn(driver.artifact_id, assessment.artifact_id, "archimate-influence")],
        "archimate-motivation",
        tmp_path,
    )

    # A lone connectionless element carries its own label already — a one-element
    # type box would only add a meaningless frame around it.
    assert "<<MotivationGrouping>>" not in puml
    assert "DRV_B" in puml


def test_render_body_never_interleaves_unrelated_flows(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    a1 = _entity("FNC@1.a.first-a", "driver", "First A", "FNC_A1", subdomain="drivers")
    a2 = _entity("FNC@1.b.second-a", "driver", "Second A", "FNC_A2", subdomain="drivers")
    b1 = _entity("FNC@2.a.first-b", "assessment", "First B", "FNC_B1", subdomain="assessments")
    b2 = _entity("FNC@2.b.second-b", "assessment", "Second B", "FNC_B2", subdomain="assessments")

    puml = renderer.render_body(
        "Two Flows",
        [a1, b1, a2, b2],  # arrival order interleaves the two chains on purpose
        [
            _conn(a1.artifact_id, a2.artifact_id, "archimate-triggering"),
            _conn(b1.artifact_id, b2.artifact_id, "archimate-triggering"),
        ],
        "archimate-motivation",
        tmp_path,
    )

    # The two chains stay unmixed: each pair chains contiguously within its own
    # layer, and no hidden chain ever joins a member of one chain to the other's.
    assert "FNC_A1 -[hidden]right- FNC_A2" in puml
    assert "FNC_B1 -[hidden]right- FNC_B2" in puml
    for mixed in ("FNC_A1 -[hidden]right- FNC_B1", "FNC_A2 -[hidden]right- FNC_B1",
                  "FNC_B2 -[hidden]right- FNC_A1", "FNC_A1 -[hidden]down- FNC_B1"):
        assert mixed not in puml


def test_render_body_orders_source_before_target_within_component(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    source = _entity(
        "SSW@1.a.registry",
        "system-software",
        "Registry",
        "SSW_REG",
        domain="technology",
        subdomain="system-software",
    )
    target = _entity(
        "NOD@1.a.cluster",
        "technology-node",
        "Cluster",
        "NOD_CLU",
        domain="technology",
        subdomain="technology-nodes",
    )

    puml = renderer.render_body(
        "Registry Access",
        [source, target],
        [_conn(source.artifact_id, target.artifact_id, "archimate-serving")],
        "archimate-technology",
        tmp_path,
    )

    # Provider sits above consumer along the component chain, so the arrow needs no
    # direction compensation at all (the old type grouping put the target first and
    # had to bend the arrow back up).
    assert "SSW_REG -[hidden]down- NOD_CLU" not in puml  # rank rides on the arrow hint
    assert "SSW_REG -down-> NOD_CLU" in puml


def test_archimate_renderer_keeps_connection_text_hidden_by_default(tmp_path: Path) -> None:
    renderer = ArchimatePumlRenderer(_ARCHIMATE_CONFIG)
    source = _entity(
        "SSW@1.a.registry",
        "system-software",
        "Registry",
        "SSW_REG",
        domain="technology",
        subdomain="system-software",
    )
    target = _entity(
        "NOD@1.a.cluster",
        "technology-node",
        "Cluster",
        "NOD_CLU",
        domain="technology",
        subdomain="technology-nodes",
    )

    puml = renderer.render_body(
        "Registry Access",
        [source, target],
        [_conn(source.artifact_id, target.artifact_id, "archimate-serving", content_text="HTTPS 443")],
        "archimate-technology",
        tmp_path,
    )

    assert "SSW_REG -down-> NOD_CLU" in puml
    assert "HTTPS 443" not in puml


def test_archimate_renderer_renders_only_selected_connection_annotation_content(tmp_path: Path) -> None:
    renderer = ArchimatePumlRenderer(_ARCHIMATE_CONFIG)
    source = _entity(
        "SSW@1.a.registry",
        "system-software",
        "Registry",
        "SSW_REG",
        domain="technology",
        subdomain="system-software",
    )
    target = _entity(
        "NOD@1.a.cluster",
        "technology-node",
        "Cluster",
        "NOD_CLU",
        domain="technology",
        subdomain="technology-nodes",
    )
    connection = _conn(
        source.artifact_id,
        target.artifact_id,
        "archimate-serving",
        content_text="Registry pulls over HTTPS 443",
        src_multiplicity="1",
        tgt_multiplicity="0..*",
    )

    puml = renderer.render_body(
        "Registry Access",
        [source, target],
        [connection],
        "archimate-technology",
        tmp_path,
        diagram_connections=[
            {
                "artifact_id": connection.artifact_id,
                "include_description": True,
                "label": "Outbound TCP",
            }
        ],
    )

    assert "SSW_REG -down-> NOD_CLU : Registry pulls over HTTPS 443 | Outbound TCP" in puml


def test_archimate_renderer_can_opt_in_multiplicity_for_annotated_connections(tmp_path: Path) -> None:
    renderer = ArchimatePumlRenderer(_ARCHIMATE_CONFIG)
    source = _entity("OUT@1.a.outcome", "outcome", "Outcome A", "OUT_A")
    target = _entity("GOL@1.a.goal", "goal", "Goal A", "GOL_A", subdomain="goals")
    connection = _conn(
        source.artifact_id,
        target.artifact_id,
        "archimate-realization",
        src_multiplicity="1",
        tgt_multiplicity="0..*",
    )

    puml = renderer.render_body(
        "Outcome Mapping",
        [source, target],
        [connection],
        "archimate-motivation",
        tmp_path,
        diagram_connections=[
            {
                "artifact_id": connection.artifact_id,
                "include_multiplicity": True,
                "label": "Required path",
            }
        ],
    )

    assert "OUT_A .up.|> GOL_A : 1 -> 0..* | Required path" in puml


def test_archimate_connections_use_ontology_arrow_styles_not_macros(tmp_path: Path) -> None:
    """ArchiMate connections must render with the type-specific puml_arrow from the ontology.

    Each ArchiMate relationship has a distinct PlantUML arrow notation:
    - association  → '--'   (undirected solid line)
    - realization  → '..|>' (dashed hollow triangle)
    - influence    → '..>'  (dashed directed line)
    - serving      → '-->'  (solid directed line)
    - specialization → '--|>' (solid hollow triangle)

    No Rel_* macro calls must appear — those require a PlantUML ArchiMate stdlib
    that is not present in the workspace.
    """
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    src = _entity("GOL@1.a.goal", "goal", "Goal", "GOL_A")
    tgt = _entity("OUT@1.b.outcome", "outcome", "Outcome", "OUT_A", subdomain="outcomes")

    # Each connection type has a distinct arrow family encoded in puml_arrow.
    # Direction hints may alter the middle of the arrow (e.g. ..|> → .down.|>,
    # -- → -down-) but the line-style (solid vs dashed) and arrowhead type
    # (open >, hollow |>, none) are preserved.
    #
    # Verification strategy per type:
    #   realization   — dashed line with hollow triangle: contains ".|>"
    #   influence     — dashed line with open arrowhead: contains ".>" but not ".|>"
    #   association   — undirected solid line: NO arrowhead character (no ">" or "|>")
    #   serving       — solid directed open arrowhead: contains "->" but not "-|>"
    #   specialization— solid line with hollow triangle: contains "-|>"
    cases: list[tuple[str, str | None, str | None]] = [
        ("archimate-realization",   ".|>",  None),
        ("archimate-influence",     ".>",   None),
        ("archimate-association",   None,   ">"),   # None=must-contain, ">"=must-NOT-contain
        ("archimate-serving",       "->",   None),
        ("archimate-specialization", "-|>", None),
    ]
    for conn_type, must_contain, must_not_contain in cases:
        puml = renderer.render_body(
            "Test",
            [src, tgt],
            [_conn(src.artifact_id, tgt.artifact_id, conn_type)],
            "archimate-motivation",
            tmp_path,
        )
        conn_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln and "OUT_A" in ln and "[hidden]" not in ln]
        assert conn_lines, f"{conn_type!r}: no connection line found in PUML"
        if must_contain is not None:
            assert any(must_contain in ln for ln in conn_lines), (
                f"{conn_type!r} should contain {must_contain!r} in connection line, got: {conn_lines}"
            )
        if must_not_contain is not None:
            assert all(must_not_contain not in ln for ln in conn_lines), (
                f"{conn_type!r} must NOT contain {must_not_contain!r} (undirected), got: {conn_lines}"
            )
        assert "Rel_" not in puml, f"{conn_type!r} must not generate Rel_* macro calls"
        assert f"<<{conn_type.removeprefix('archimate-')}>>" not in puml, (
            f"{conn_type!r} must not emit stereotype label — arrow style conveys the type"
        )


def test_influence_polarity_renders_as_colored_sign(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    source = _entity("DRV@1.a.driver", "driver", "Driver", "DRV_A", subdomain="drivers")
    target = _entity("GOL@1.a.goal", "goal", "Goal", "GOL_A", subdomain="goals")

    positive = renderer.render_body(
        "Positive influence",
        [source, target],
        [_conn(source.artifact_id, target.artifact_id, "archimate-influence", attributes={"polarity": "positive"})],
        "archimate-motivation",
        tmp_path,
    )
    negative = renderer.render_body(
        "Negative influence",
        [source, target],
        [_conn(source.artifact_id, target.artifact_id, "archimate-influence", attributes={"polarity": "negative"})],
        "archimate-motivation",
        tmp_path,
    )

    assert "<color:#15803d><b>+</b></color>" in positive
    assert "<color:#b91c1c><b>-</b></color>" in negative


def test_render_body_renders_junction_inside_nested_parent(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    process = _entity("PRC@1.a.process-a", "process", "Process A", "PRC_A", domain="business", subdomain="processes")
    function_a = _entity(
        "FNC@1.a.function-a", "function", "Function A", "FNC_A", domain="business", subdomain="functions"
    )
    function_b = _entity(
        "FNC@1.b.function-b", "function", "Function B", "FNC_B", domain="business", subdomain="functions"
    )
    junction = _entity("JNA@1.a.and-a", "and-junction", "AND A", "JNA_A", domain="business", subdomain="junctions")

    puml = renderer.render_body(
        "Nested Junction",
        [process, function_a, function_b, junction],
        [
            _conn(process.artifact_id, function_a.artifact_id, "archimate-composition"),
            _conn(process.artifact_id, function_b.artifact_id, "archimate-composition"),
            _conn(function_a.artifact_id, junction.artifact_id, "archimate-flow"),
            _conn(junction.artifact_id, function_b.artifact_id, "archimate-flow"),
        ],
        "archimate-business",
        tmp_path,
    )

    # Process rendered as inline opening rectangle with brace
    assert '<<process>> as PRC_A {' in puml
    assert 'circle " " as JNA_A' in puml
    assert "$NEST_PRC_A()" not in puml
    # Verify junction is nested inside process by checking indentation
    lines = puml.splitlines()
    in_prc = False
    junction_nested = False
    for line in lines:
        if '<<process>> as PRC_A {' in line:
            in_prc = True
        elif in_prc and line.strip() == "}":
            in_prc = False
        elif in_prc and "JNA_A" in line:
            junction_nested = True
    assert junction_nested, "Junction should appear nested inside PRC_A block"


def test_render_body_entity_declarations_use_snake_case_stereotypes(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    stakeholder = _entity("STK@1.a.stakeholder-a", "stakeholder", "Stakeholder A", "STK_A", subdomain="stakeholders")
    value = _entity("VAL@1.a.value-a", "value", "Value A", "VAL_A", subdomain="values")

    puml = renderer.render_body(
        "Declaration Patterns",
        [stakeholder, value],
        [],
        "archimate-motivation",
        tmp_path,
    )

    # Inline rectangle declarations with stereotype — not macro calls
    assert '<<stakeholder>> as STK_A' in puml
    assert '<<value>> as VAL_A' in puml
    assert "$DECL_" not in puml
    assert "$NEST_" not in puml


def test_render_body_multi_domain_with_connections_does_not_crash(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    app = _entity(
        "APP@1.a.app-a", "application-component", "App A", "APP_A", domain="application", subdomain="components"
    )
    node = _entity("NOD@1.a.node-a", "technology-node", "Node A", "NOD_A", domain="technology", subdomain="nodes")

    # Multi-domain scenario — must not raise UnboundLocalError
    puml = renderer.render_body(
        "Multi Domain",
        [app, node],
        [_conn(app.artifact_id, node.artifact_id, "archimate-serving")],
        "archimate-layered",
        tmp_path,
    )

    assert "APP_A" in puml
    assert "NOD_A" in puml


def test_render_body_adds_archimate_occurrence_aliases(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    repo = _entity("BOB@1.a.repo", "business-object", "Repository", "BOB_REPO", domain="business")

    puml = renderer.render_body(
        "Repository Occurrences",
        [repo],
        [],
        "archimate-business",
        tmp_path,
        diagram_entities={
            "occurrence": [
                {"id": "repo-left", "backing_entity_id": repo.artifact_id},
                {"id": "repo-right", "backing_entity_id": repo.artifact_id},
            ]
        },
    )

    assert "<<business_object>> as BOB_REPO" in puml
    assert "<<business_object>> as BOB_REPO__2" in puml
    assert "<<business_object>> as BOB_REPO__3" in puml


def test_render_body_connections_default_to_primary_occurrence(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    repo = _entity("BOB@1.a.repo", "business-object", "Repository", "BOB_REPO", domain="business")
    process = _entity("PRC@1.a.promote", "process", "Promote", "PRC_PROMOTE", domain="business")

    puml = renderer.render_body(
        "Repository Occurrences",
        [repo, process],
        [_conn(process.artifact_id, repo.artifact_id, "archimate-access")],
        "archimate-business",
        tmp_path,
        diagram_entities={
            "occurrence": [
                {"id": "repo-left", "backing_entity_id": repo.artifact_id}
            ]
        },
    )

    conn_lines = [line for line in puml.splitlines() if "PRC_PROMOTE" in line and "BOB_REPO" in line]
    assert any("PRC_PROMOTE" in line and "BOB_REPO" in line for line in conn_lines)
    assert all("BOB_REPO__2" not in line for line in conn_lines)


def _derived_conn(source: str, target: str, conn_type: str, *, path_key: str, certainty: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=f"derived::{conn_type}::{path_key}",
        source=source,
        target=target,
        conn_type=conn_type,
        version="",
        status="",
        path=Path(),
        extra={"certainty": certainty},
        content_text="",
    )


def test_derived_connection_renders_dashed_when_certain(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    src = _entity("GOL@1.a.goal", "goal", "Goal", "GOL_A")
    tgt = _entity("OUT@1.b.outcome", "outcome", "Outcome", "OUT_A", subdomain="outcomes")

    puml = renderer.render_body(
        "Test",
        [src, tgt],
        [
            _derived_conn(
                src.artifact_id, tgt.artifact_id, "archimate-realization", path_key="c1@fwd", certainty="certain"
            )
        ],
        "archimate-motivation",
        tmp_path,
    )

    conn_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln and "OUT_A" in ln]
    assert any("[dashed]" in ln for ln in conn_lines)


def test_derived_connection_renders_dotted_when_potential(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    src = _entity("GOL@1.a.goal", "goal", "Goal", "GOL_A")
    tgt = _entity("OUT@1.b.outcome", "outcome", "Outcome", "OUT_A", subdomain="outcomes")

    puml = renderer.render_body(
        "Test",
        [src, tgt],
        [
            _derived_conn(
                src.artifact_id, tgt.artifact_id, "archimate-serving", path_key="c1@fwd", certainty="potential"
            )
        ],
        "archimate-motivation",
        tmp_path,
    )

    conn_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln and "OUT_A" in ln]
    assert any("[dotted]" in ln for ln in conn_lines)


def test_modeled_connection_unaffected_by_derived_marker_logic(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    src = _entity("GOL@1.a.goal", "goal", "Goal", "GOL_A")
    tgt = _entity("OUT@1.b.outcome", "outcome", "Outcome", "OUT_A", subdomain="outcomes")

    puml = renderer.render_body(
        "Test", [src, tgt], [_conn(src.artifact_id, tgt.artifact_id, "archimate-serving")], "archimate-motivation",
        tmp_path,
    )

    conn_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln and "OUT_A" in ln]
    assert all("[dashed]" not in ln and "[dotted]" not in ln for ln in conn_lines)


def test_label_attribute_shows_the_attribute_value_under_the_entity_label(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    entity = _entity("GOL@1.a.goal", "goal", "Goal A", "GOL_A", extra={"risk_score": 5})

    puml = renderer.render_body("Test", [entity], [], "archimate-motivation", tmp_path, label_attribute="risk_score")

    entity_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln]
    assert any('Goal A\\n5"' in ln for ln in entity_lines)


def test_label_attribute_omitted_by_default(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    entity = _entity("GOL@1.a.goal", "goal", "Goal A", "GOL_A", extra={"risk_score": 5})

    puml = renderer.render_body("Test", [entity], [], "archimate-motivation", tmp_path)

    entity_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln]
    assert all("risk_score" not in ln and "\\n5" not in ln for ln in entity_lines)


def test_label_attribute_missing_on_entity_is_a_silent_no_op(tmp_path: Path) -> None:
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
    entity = _entity("GOL@1.a.goal", "goal", "Goal A", "GOL_A", extra={})

    puml = renderer.render_body("Test", [entity], [], "archimate-motivation", tmp_path, label_attribute="risk_score")

    entity_lines = [ln for ln in puml.splitlines() if "GOL_A" in ln]
    assert any("Goal A" in ln for ln in entity_lines)
    assert all("\\n" not in ln for ln in entity_lines)


def test_inject_includes_inlines_only_needed_stereotypes_and_sprites(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog = repo_root / "diagram-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        """\
' Grouping containers.
!include <archimate/Archimate>
hide stereotype
skinparam rectangle<<Process>> {
  BackgroundColor #E0D8CC
  BorderColor #8C7E6A
}
""",
        encoding="utf-8",
    )
    (catalog / "_archimate-glyphs.puml").write_text(
        'sprite $archimate_Process <svg xmlns="http://www.w3.org/2000/svg"></svg>\n',
        encoding="utf-8",
    )
    renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)

    result = renderer.inject_includes(
        """\
@startuml test
!include ../_archimate-stereotypes.puml
!include ../_archimate-glyphs.puml
rectangle "<$archimate_Process{scale=1.5}> Proc" <<Process>> as PROC_A
@enduml
""",
        repo_root,
    )

    assert "Grouping containers" not in result
    assert "hide stereotype" in result
    assert "skinparam rectangle<<Process>>" in result
    assert "sprite $archimate_Process" in result
    assert "!include ../_archimate-glyphs.puml" not in result
