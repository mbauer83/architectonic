from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.mcp.artifact_mcp.query_scaffold_tools import artifact_diagram_scaffold
from src.infrastructure.rendering.archimate_relation_rendering import format_multiplicity_label
from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body, inject_archimate_includes
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from src.infrastructure.write.artifact_write.diagram import _prepare_diagram_puml_body


def _entity(
    artifact_id: str,
    artifact_type: str,
    name: str,
    alias: str,
    *,
    domain: str = "motivation",
    subdomain: str = "goals",
) -> EntityRecord:
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
        extra={},
        content_text="",
        display_blocks={},
        display_label=name,
        display_alias=alias,
    )


def _conn(
    source: str,
    target: str,
    conn_type: str = "archimate-realization",
    *,
    src_multiplicity: str = "",
    tgt_multiplicity: str = "",
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
        src_multiplicity=src_multiplicity,
        tgt_multiplicity=tgt_multiplicity,
    )


def test_generate_archimate_puml_body_normalizes_aliases_in_entities_and_connections() -> None:
    goal = _entity(
        "GOL@1.B6G_-P.support-technology-design-for-ai",
        "goal",
        "Support Technology Design for AI",
        "GOL_B6G_-P",
    )
    outcome = _entity(
        "OUT@1.i-3Bi-.ai-agents-query-technology-architecture",
        "outcome",
        "AI Agents Query Technology Architecture to Identify Constraints",
        "OUT_i-3Bi-",
        subdomain="outcomes",
    )

    puml = generate_archimate_puml_body(
        "Alias Test",
        [goal, outcome],
        [_conn(outcome.artifact_id, goal.artifact_id)],
        diagram_type="archimate-motivation",
    )

    assert '<<goal>> as GOL_B6G__P' in puml
    assert '<<outcome>> as OUT_i_3Bi_' in puml
    assert "OUT_i_3Bi_ .up.|> GOL_B6G__P" in puml
    assert "GOL_B6G_-P" not in puml
    assert "OUT_i-3Bi-" not in puml


def test_generate_archimate_puml_body_groups_single_domain_by_component() -> None:
    driver_a = _entity("DRV@1.a.driver-a", "driver", "Driver A", "DRV_A", subdomain="drivers")
    driver_b = _entity("DRV@1.b.driver-b", "driver", "Driver B", "DRV_B", subdomain="drivers")
    assessment = _entity(
        "ASS@1.a.assessment-a",
        "assessment",
        "Assessment A",
        "ASS_A",
        subdomain="assessments",
    )

    puml = generate_archimate_puml_body(
        "Drivers and Assessments",
        [driver_a, driver_b, assessment],
        [
            _conn(driver_a.artifact_id, assessment.artifact_id, "archimate-influence"),
            _conn(driver_b.artifact_id, driver_a.artifact_id, "archimate-association"),
        ],
        diagram_type="archimate-motivation",
    )

    # A non-flow component reads as TYPE LAYERS: drivers above the assessment they
    # influence, members spread along the layer; a singleton layer stands bare.
    assert 'rectangle "Drivers" <<MotivationGrouping>> as GRPT_' in puml
    assert "top to bottom direction" in puml
    assert "DRV_A -[hidden]right- DRV_B" in puml
    assert "GRPT_1 -[hidden]down- ASS_A" not in puml  # connected units rank via arrow hints
    assert "DRV_A .down.> ASS_A" in puml


def test_inject_archimate_includes_strips_comment_header_text(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog = repo_root / "diagram-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        """\
' Grouping containers.
' Use the layer-specific stereotype when all contained elements belong to one layer.
!include <archimate/Archimate>
hide stereotype
skinparam rectangle<<Requirement>> {
  BackgroundColor #EDD6F0
  BorderColor #7B3F9A
}
""",
        encoding="utf-8",
    )

    puml = """\
@startuml test
!include ../_archimate-stereotypes.puml
rectangle "Req" <<Requirement>> as REQ_A
@enduml
"""
    result = inject_archimate_includes(puml, repo_root)

    assert "Grouping containers" not in result
    assert "Use the layer-specific stereotype" not in result
    assert "hide stereotype" in result
    assert "skinparam rectangle<<Requirement>>" in result


def test_inject_archimate_includes_inlines_relation_macros(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog = repo_root / "diagram-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        "hide stereotype\nskinparam rectangle<<Process>> {\n  BackgroundColor #E0D8CC\n}\n",
        encoding="utf-8",
    )
    (catalog / "_archimate-relations.puml").write_text(
        "' relations\n"
        "!define Rel_Triggering(from, to, label) from --> to\n"
        "!define Rel_Serving(from, to, label) from --> to\n",
        encoding="utf-8",
    )

    puml = """\
@startuml test
!include ../_archimate-stereotypes.puml
!include ../_archimate-relations.puml
rectangle "A" <<Process>> as PRC_A
rectangle "B" <<Process>> as PRC_B
Rel_Triggering(PRC_A, PRC_B, "")
@enduml
"""
    result = inject_archimate_includes(puml, repo_root)

    assert "!include ../_archimate-stereotypes.puml" not in result
    assert "!include ../_archimate-relations.puml" not in result
    assert "!define Rel_Triggering(from, to, label) from --> to" in result
    assert "!define Rel_Serving(from, to, label) from --> to" in result
    assert "Rel_Triggering(PRC_A, PRC_B" in result


def test_inject_archimate_includes_relations_file_missing_is_noop(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog = repo_root / "diagram-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        "hide stereotype\nskinparam rectangle<<Process>> {\n  BackgroundColor #E0D8CC\n}\n",
        encoding="utf-8",
    )

    puml = """\
@startuml test
!include ../_archimate-stereotypes.puml
rectangle "A" <<Process>> as PRC_A
@enduml
"""
    result = inject_archimate_includes(puml, repo_root)

    assert "!include ../_archimate-stereotypes.puml" not in result
    assert "hide stereotype" in result
    assert "skinparam rectangle<<Process>>" in result


def test_prepare_diagram_puml_body_injects_renderer_assets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog = repo_root / "diagram-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    (catalog / "_archimate-stereotypes.puml").write_text(
        """\
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

    puml = """\
@startuml test
rectangle "<$archimate_Process{scale=1.5}> Proc" <<Process>> as PROC_A
@enduml
"""
    result = _prepare_diagram_puml_body(puml, repo_root, "archimate-layered")

    assert "!include ../_archimate-stereotypes.puml" not in result
    assert "sprite $archimate_Process" in result
    assert 'rectangle "<$archimate_Process{scale=1.5}> Proc" <<Process>> as PROC_A' in result


def test_generate_static_includes_writes_glyph_and_stereotype_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "diagram-catalog").mkdir(parents=True)
    (repo_root / "model").mkdir()

    generate_static_includes(repo_root)

    stereo = (repo_root / "diagram-catalog" / "_archimate-stereotypes.puml").read_text()
    glyphs = (repo_root / "diagram-catalog" / "_archimate-glyphs.puml").read_text()
    assert "skinparam rectangle<<driver>>" in stereo
    assert "skinparam rectangle<<goal>>" in stereo
    assert "hide stereotype" in stereo or "hide stereotype" in glyphs


def test_model_diagram_scaffold_uses_canonical_aliases(tmp_path: Path) -> None:
    repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    goal_id = "GOL@1.B6G_-P.support-technology-design-for-ai"
    outcome_id = "OUT@1.i-3Bi-.ai-agents-query-technology-architecture"
    goal_path = repo_root / "model" / "motivation" / "goal" / f"{goal_id}.md"
    outcome_path = repo_root / "model" / "motivation" / "outcome" / f"{outcome_id}.md"
    outgoing_path = repo_root / "model" / "motivation" / "outcome" / f"{outcome_id}.outgoing.md"

    goal_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_path.parent.mkdir(parents=True, exist_ok=True)
    goal_path.write_text(
        f"""\
---
artifact-id: {goal_id}
artifact-type: goal
name: "Support Technology Design for AI"
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §content -->

## Support Technology Design for AI

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Goal
label: "Support Technology Design for AI"
alias: GOL_B6G_-P
```
""",
        encoding="utf-8",
    )
    outcome_path.write_text(
        f"""\
---
artifact-id: {outcome_id}
artifact-type: outcome
name: "AI Agents Query Technology Architecture to Identify Constraints"
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §content -->

## AI Agents Query Technology Architecture to Identify Constraints

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Outcome
label: "AI Agents Query Technology Architecture to Identify Constraints"
alias: OUT_i-3Bi-
```
""",
        encoding="utf-8",
    )
    outgoing_path.write_text(
        f"""\
---
source-entity: {outcome_id}
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §connections -->

### archimate-realization → {goal_id}
""",
        encoding="utf-8",
    )

    result = artifact_diagram_scaffold(
        entity_ids=[goal_id, outcome_id],
        diagram_name="Alias Scaffold",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    puml = str(result["puml"])

    assert '<<goal>> as GOL_B6G__P' in puml
    assert '<<outcome>> as OUT_i_3Bi_' in puml
    assert "OUT_i_3Bi_ .up.|> GOL_B6G__P" in puml
    assert "GOL_B6G_-P" not in puml
    assert "OUT_i-3Bi-" not in puml


def test_model_diagram_scaffold_groups_single_domain_by_component(tmp_path: Path) -> None:
    repo_root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    driver_id = "DRV@1.a.driver-a"
    assessment_id = "ASS@1.a.assessment-a"
    driver_path = repo_root / "model" / "motivation" / "driver" / f"{driver_id}.md"
    assessment_path = repo_root / "model" / "motivation" / "assessment" / f"{assessment_id}.md"
    outgoing_path = repo_root / "model" / "motivation" / "driver" / f"{driver_id}.outgoing.md"

    driver_path.parent.mkdir(parents=True, exist_ok=True)
    assessment_path.parent.mkdir(parents=True, exist_ok=True)
    driver_path.write_text(
        f"""\
---
artifact-id: {driver_id}
artifact-type: driver
name: "Driver A"
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §content -->

## Driver A

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Driver
label: "Driver A"
alias: DRV_A
```
""",
        encoding="utf-8",
    )
    assessment_path.write_text(
        f"""\
---
artifact-id: {assessment_id}
artifact-type: assessment
name: "Assessment A"
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §content -->

## Assessment A

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Assessment
label: "Assessment A"
alias: ASS_A
```
""",
        encoding="utf-8",
    )
    outgoing_path.write_text(
        f"""\
---
source-entity: {driver_id}
version: 0.1.0
status: draft
last-updated: '2026-04-20'
---

<!-- §connections -->

### archimate-influence → {assessment_id}
""",
        encoding="utf-8",
    )

    result = artifact_diagram_scaffold(
        entity_ids=[driver_id, assessment_id],
        diagram_name="Drivers and Assessments",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    puml = str(result["puml"])

    # Connected elements group by connection component, not element type — no
    # domain box AND no type boxes for elements that have connections.
    assert "<<MotivationGrouping>>" not in puml
    assert "top to bottom direction" in puml
    assert "DRV_A .down.> ASS_A" in puml
    assert "DRV_A .down.> ASS_A" in puml


# ── format_multiplicity_label unit tests ───────────────────────────────────────


def test_format_multiplicity_label_both_ends() -> None:
    assert format_multiplicity_label("1", "0..*") == "1 -> 0..*"


def test_format_multiplicity_label_src_only() -> None:
    assert format_multiplicity_label("1", "") == "1 ->"


def test_format_multiplicity_label_tgt_only() -> None:
    assert format_multiplicity_label("", "*") == "-> *"


def test_format_multiplicity_label_neither() -> None:
    assert format_multiplicity_label("", "") == ""


# ── generate_archimate_puml_body multiplicity rendering ───────────────────────


def test_generate_archimate_puml_body_renders_multiplicity_both_ends() -> None:
    goal = _entity("GOL@1.a.goal-a", "goal", "Goal A", "GOL_A")
    outcome = _entity("OUT@1.a.outcome-a", "outcome", "Outcome A", "OUT_A", subdomain="outcomes")
    conn = _conn(
        outcome.artifact_id,
        goal.artifact_id,
        "archimate-realization",
        src_multiplicity="1",
        tgt_multiplicity="0..*",
    )

    puml = generate_archimate_puml_body("Test", [goal, outcome], [conn])

    assert "1 -> 0..*" in puml
    assert "OUT_A .up.|> GOL_A : 1 -> 0..*" in puml


def test_generate_archimate_puml_body_renders_multiplicity_src_only() -> None:
    goal = _entity("GOL@1.a.goal-a", "goal", "Goal A", "GOL_A")
    outcome = _entity("OUT@1.a.outcome-a", "outcome", "Outcome A", "OUT_A", subdomain="outcomes")
    conn = _conn(
        outcome.artifact_id,
        goal.artifact_id,
        "archimate-realization",
        src_multiplicity="1",
    )

    puml = generate_archimate_puml_body("Test", [goal, outcome], [conn])

    assert "OUT_A .up.|> GOL_A : 1 ->" in puml


def test_generate_archimate_puml_body_no_multiplicity_keeps_empty_label() -> None:
    goal = _entity("GOL@1.a.goal-a", "goal", "Goal A", "GOL_A")
    outcome = _entity("OUT@1.a.outcome-a", "outcome", "Outcome A", "OUT_A", subdomain="outcomes")
    conn = _conn(outcome.artifact_id, goal.artifact_id, "archimate-realization")

    puml = generate_archimate_puml_body("Test", [goal, outcome], [conn])

    assert "OUT_A .up.|> GOL_A" in puml


def test_generate_archimate_puml_body_nests_junction_with_nested_siblings() -> None:
    process = _entity("PRC@1.a.process-a", "process", "Process A", "PRC_A", domain="business", subdomain="processes")
    function_a = _entity(
        "FNC@1.a.function-a", "function", "Function A", "FNC_A", domain="business", subdomain="functions"
    )
    function_b = _entity(
        "FNC@1.b.function-b", "function", "Function B", "FNC_B", domain="business", subdomain="functions"
    )
    junction = _entity("JCN@1.a.and-a", "and-junction", "AND A", "JCN_A", domain="business", subdomain="junctions")

    puml = generate_archimate_puml_body(
        "Nested Junction",
        [process, function_a, function_b, junction],
        [
            _conn(process.artifact_id, function_a.artifact_id, "archimate-composition"),
            _conn(process.artifact_id, function_b.artifact_id, "archimate-composition"),
            _conn(function_a.artifact_id, junction.artifact_id, "archimate-flow"),
            _conn(junction.artifact_id, function_b.artifact_id, "archimate-flow"),
        ],
        diagram_type="archimate-business",
    )

    assert '<<process>> as PRC_A {' in puml  # process rendered as inline nesting container
    assert "FNC_A" in puml
    assert "FNC_B" in puml
    assert 'circle " " as JCN_A' in puml
    # Verify junction is nested inside PRC_A block
    lines = puml.splitlines()
    in_prc, junction_nested = False, False
    for line in lines:
        if '<<process>> as PRC_A {' in line:
            in_prc = True
        elif in_prc and line.strip() == "}":
            in_prc = False
        elif in_prc and "JCN_A" in line:
            junction_nested = True
    assert junction_nested, "Junction should appear nested inside PRC_A block"
    assert "FNC_A ..> JCN_A" in puml
    assert "JCN_A ..> FNC_B" in puml


def test_generate_archimate_puml_body_layouts_branch_step_perpendicular_to_main_flow() -> None:
    process = _entity("PRC@1.a.process-a", "process", "Process A", "PRC_A", domain="business", subdomain="processes")
    start = _entity("FNC@1.a.start", "function", "Start", "FNC_START", domain="business", subdomain="functions")
    branch_a = _entity("FNC@1.b.branch-a", "function", "Branch A", "FNC_A", domain="business", subdomain="functions")
    branch_b = _entity("FNC@1.c.branch-b", "function", "Branch B", "FNC_B", domain="business", subdomain="functions")
    end = _entity("FNC@1.d.end", "function", "End", "FNC_END", domain="business", subdomain="functions")
    fork = _entity("JNA@1.a.fork", "and-junction", "Fork", "JNA_FORK", domain="business", subdomain="junctions")
    join = _entity("JNA@1.b.join", "and-junction", "Join", "JNA_JOIN", domain="business", subdomain="junctions")

    puml = generate_archimate_puml_body(
        "Branch Step",
        [process, start, branch_a, branch_b, end, fork, join],
        [
            _conn(process.artifact_id, start.artifact_id, "archimate-composition"),
            _conn(process.artifact_id, branch_a.artifact_id, "archimate-composition"),
            _conn(process.artifact_id, branch_b.artifact_id, "archimate-composition"),
            _conn(process.artifact_id, end.artifact_id, "archimate-composition"),
            _conn(start.artifact_id, fork.artifact_id, "archimate-triggering"),
            _conn(fork.artifact_id, branch_a.artifact_id, "archimate-triggering"),
            _conn(fork.artifact_id, branch_b.artifact_id, "archimate-triggering"),
            _conn(branch_a.artifact_id, join.artifact_id, "archimate-triggering"),
            _conn(branch_b.artifact_id, join.artifact_id, "archimate-triggering"),
            _conn(join.artifact_id, end.artifact_id, "archimate-triggering"),
        ],
        diagram_type="archimate-business",
    )

    assert "FNC_START -[hidden]right- JNA_FORK" in puml
    assert "FNC_A -[hidden]down- FNC_B" in puml
    assert "JNA_FORK -[hidden]right- FNC_A" in puml
    assert "JNA_FORK -[hidden]right- FNC_B" in puml
    assert "FNC_A -[hidden]right- JNA_JOIN" in puml
    assert "FNC_B -[hidden]right- JNA_JOIN" in puml
    assert "JNA_JOIN -[hidden]right- FNC_END" in puml


def test_domain_order_follows_declared_archimate_layer_hierarchy() -> None:
    """Multi-domain canvases stack by the ontology-declared layer order: motivation
    above strategy, both above business/common/application/technology."""
    from src.infrastructure.app_bootstrap import get_module_registry

    order = get_module_registry().domain_order()
    expected_prefix = ["motivation", "strategy", "business", "common", "application", "technology"]
    positions = [order.index(domain) for domain in expected_prefix if domain in order]
    assert positions == sorted(positions)
    assert order.index("motivation") < order.index("business")
    assert order.index("strategy") < order.index("common")
