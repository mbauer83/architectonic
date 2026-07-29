from __future__ import annotations

from pathlib import Path

import pytest

from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.infrastructure.rendering.puml_safety import strip_leading_puml_frontmatter


def _r(**kwargs: object) -> ActivityPumlRenderer:
    return ActivityPumlRenderer(dict(kwargs))


def _note_kc(note_id: str, step_id: str) -> dict[str, object]:
    return {"id": f"kc-{note_id}-{step_id}", "conn_type": "step-note-of", "source": note_id, "target": step_id}


def _lane_kc(step_id: str, lane_id: str) -> dict[str, object]:
    return {"id": f"kc-lane-{step_id}-{lane_id}", "conn_type": "step-in-lane", "source": step_id, "target": lane_id}


def _flow(source: str, target: str) -> dict[str, object]:
    return {"id": f"kc-flow-{source}-{target}", "conn_type": "step-flow", "source": source, "target": target}


def _then(decision_id: str, step_id: str) -> dict[str, object]:
    return {"id": f"kc-then-{decision_id}-{step_id}", "conn_type": "step-then",
            "source": decision_id, "target": step_id}


def _else(decision_id: str, step_id: str) -> dict[str, object]:
    return {"id": f"kc-else-{decision_id}-{step_id}", "conn_type": "step-else",
            "source": decision_id, "target": step_id}


def _fork_branch(fork_id: str, step_id: str) -> dict[str, object]:
    return {"id": f"kc-fork-{fork_id}-{step_id}", "conn_type": "step-fork-branch", "source": fork_id, "target": step_id}


def _contains(partition_id: str, step_id: str) -> dict[str, object]:
    return {"id": f"kc-contains-{partition_id}-{step_id}", "conn_type": "step-contains",
            "source": partition_id, "target": step_id}


def _render(
    diagram_entities: object = None,
    name: str = "Flow",
    diagram_connections: list[dict[str, object]] | None = None,
    **kwargs: object,
) -> str:
    return _r(**kwargs).render_body(  # type: ignore[arg-type]
        name, [], [], "activity", Path("/tmp"),
        diagram_entities=diagram_entities, diagram_connections=diagram_connections,
    )


def test_empty_kind_data_renders_start_stop() -> None:
    puml = _render(diagram_entities={})
    assert "start" in puml
    assert "stop" in puml
    assert ":action;" not in puml


def test_action_step_renders_as_v2_action() -> None:
    puml = _render(diagram_entities={"action": [{"type": "action", "id": "a1", "label": "Submit Form"}]})
    assert ":[[arch://a1 Submit Form]];" in puml


_D1_VALID = {"type": "decision", "id": "d1", "condition": "Valid", "then_label": "yes", "else_label": "no"}


def test_decision_step_renders_if_then_else() -> None:
    puml = _render(
        diagram_entities={
            "decision": [_D1_VALID],
            "action": [
                {"type": "action", "id": "a1", "label": "Proceed"},
                {"type": "action", "id": "a2", "label": "Reject"},
            ],
        },
        diagram_connections=[_then("d1", "a1"), _else("d1", "a2")],
    )
    assert "if ([[arch://d1 Valid?]]) then (yes)" in puml
    assert ":[[arch://a1 Proceed]];" in puml
    assert "else (no)" in puml
    assert ":[[arch://a2 Reject]];" in puml
    assert "endif" in puml


def test_fork_step_renders_fork_again_end_fork() -> None:
    puml = _render(
        diagram_entities={
            "fork": [{"type": "fork", "id": "f1"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Branch A"},
                {"type": "action", "id": "a2", "label": "Branch B"},
            ],
        },
        diagram_connections=[_fork_branch("f1", "a1"), _fork_branch("f1", "a2")],
    )
    assert "fork\n" in puml
    assert "fork again" in puml
    assert "end fork" in puml
    assert ":[[arch://a1 Branch A]];" in puml
    assert ":[[arch://a2 Branch B]];" in puml


def test_swimlane_emitted_before_first_step_in_lane() -> None:
    puml = _render(
        diagram_entities={
            "swimlane": [
                {"id": "sw-1", "label": "Customer"},
                {"id": "sw-2", "label": "System"},
            ],
            "action": [
                {"type": "action", "id": "a1", "label": "Submit"},
                {"type": "action", "id": "a2", "label": "Process"},
            ],
        },
        diagram_connections=[_lane_kc("a1", "sw-1"), _lane_kc("a2", "sw-2"), _flow("a1", "a2")],
    )
    import re as _re

    start_pos = _re.search(r"^start$", puml, _re.MULTILINE).start()  # type: ignore[union-attr]
    customer_pos = puml.index("|Customer|")
    submit_pos = puml.index(":[[arch://a1 Submit]];")
    system_pos = puml.index("|System|")
    process_pos = puml.index(":[[arch://a2 Process]];")
    assert customer_pos < start_pos < submit_pos < system_pos < process_pos


def test_lane_not_repeated_for_consecutive_steps_in_same_lane() -> None:
    puml = _render(
        diagram_entities={
            "swimlane": [{"id": "sw-1", "label": "Lane"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Step 1"},
                {"type": "action", "id": "a2", "label": "Step 2"},
            ],
        },
        diagram_connections=[_lane_kc("a1", "sw-1"), _lane_kc("a2", "sw-1"), _flow("a1", "a2")],
    )
    assert puml.count("|Lane|") == 1


def test_unknown_lane_id_emits_no_lane_marker() -> None:
    puml = _render(
        diagram_entities={
            "swimlane": [{"id": "sw-1", "label": "Lane"}],
            "action": [{"type": "action", "id": "a1", "label": "Step"}],
        },
        diagram_connections=[_lane_kc("a1", "nonexistent")],
    )
    after_start = puml.split("start", 1)[1]
    assert "|" not in after_start


def test_step_without_lane_conn_emits_warning_comment_when_swimlanes_present() -> None:
    puml = _render(
        diagram_entities={
            "swimlane": [{"id": "sw-1", "label": "Lane"}],
            "action": [{"type": "action", "id": "a1", "label": "Orphan"}],
        },
    )
    assert "' WARNING: step 'a1' has no step-in-lane connection" in puml


def test_step_without_lane_conn_no_warning_when_no_swimlanes() -> None:
    puml = _render(
        diagram_entities={
            "action": [{"type": "action", "id": "a1", "label": "Solo"}],
        },
    )
    assert "WARNING" not in puml


def test_nested_decision_inside_decision() -> None:
    # d1.then → d2.then → a1; d2.else = empty; d1.else = empty
    puml = _render(
        diagram_entities={
            "decision": [
                {"type": "decision", "id": "d1", "condition": "Outer", "then_label": "yes", "else_label": "no"},
                {"type": "decision", "id": "d2", "condition": "Inner", "then_label": "yes", "else_label": "no"},
            ],
            "action": [{"type": "action", "id": "a1", "label": "Deep Action"}],
        },
        diagram_connections=[_then("d1", "d2"), _then("d2", "a1")],
    )
    assert puml.count("if (") == 2
    assert ":[[arch://a1 Deep Action]];" in puml


def test_decision_branch_lane_switch() -> None:
    puml = _render(
        diagram_entities={
            "swimlane": [
                {"id": "sw-1", "label": "Manager"},
                {"id": "sw-2", "label": "System"},
            ],
            "decision": [{"type": "decision", "id": "d1", "condition": "Approved",
                          "then_label": "yes", "else_label": "no"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Process"},
                {"type": "action", "id": "a2", "label": "Notify"},
            ],
        },
        diagram_connections=[
            _lane_kc("d1", "sw-1"), _lane_kc("a1", "sw-2"), _lane_kc("a2", "sw-1"),
            _then("d1", "a1"), _else("d1", "a2"),
        ],
    )
    assert "|Manager|" in puml
    assert "|System|" in puml
    assert "if ([[arch://d1 Approved?]]) then (yes)" in puml


def test_partition_step_renders_partition_block() -> None:
    puml = _render(
        diagram_entities={
            "partition": [{"type": "partition", "id": "p1", "label": "My Partition"}],
            "action": [{"type": "action", "id": "a1", "label": "Inside"}],
        },
        diagram_connections=[_contains("p1", "a1")],
    )
    assert 'partition "My Partition" [[arch://p1]] {' in puml
    assert ":[[arch://a1 Inside]];" in puml
    assert "}" in puml


def test_action_link_renders_bracket_syntax() -> None:
    puml = _render(diagram_entities={"action": [{"type": "action", "id": "a1", "label": "Go", "link": "https://example.com"}]})
    assert ":[[arch://a1 Go]] [[https://example.com]];" in puml


def test_action_link_escapes_brackets_in_url() -> None:
    puml = _render(
        diagram_entities={"action": [{"type": "action", "id": "a1", "label": "Go", "link": "https://example.com/a[1]"}]}
    )
    assert "%5D" in puml
    assert "[[" in puml


def test_note_on_action_follows_action_line() -> None:
    puml = _render(
        diagram_entities={
            "action": [{"type": "action", "id": "a1", "label": "Submit"}],
            "note": [{"id": "n1", "side": "right", "text": "Attached note"}],
        },
        diagram_connections=[_note_kc("n1", "a1")],
    )
    action_pos = puml.index(":[[arch://a1 Submit]];")
    note_pos = puml.index("note right: Attached note")
    assert action_pos < note_pos


def test_note_on_decision_precedes_then_branch() -> None:
    puml = _render(
        diagram_entities={
            "decision": [_D1_VALID],
            "action": [{"type": "action", "id": "a1", "label": "Proceed"}],
            "note": [{"id": "n1", "side": "left", "text": "Check validity"}],
        },
        diagram_connections=[_then("d1", "a1"), _note_kc("n1", "d1")],
    )
    if_pos = puml.index("if ([[arch://d1 Valid?]])")
    note_pos = puml.index("note left: Check validity")
    proceed_pos = puml.index(":[[arch://a1 Proceed]];")
    assert if_pos < note_pos < proceed_pos


def test_note_on_fork_follows_fork_keyword() -> None:
    puml = _render(
        diagram_entities={
            "fork": [{"type": "fork", "id": "f1"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Branch A"},
                {"type": "action", "id": "a2", "label": "Branch B"},
            ],
            "note": [{"id": "n1", "side": "right", "text": "Parallel work"}],
        },
        diagram_connections=[_fork_branch("f1", "a1"), _fork_branch("f1", "a2"), _note_kc("n1", "f1")],
    )
    fork_pos = puml.index("fork\n")
    note_pos = puml.index("note right: Parallel work")
    branch_pos = puml.index(":[[arch://a1 Branch A]];")
    assert fork_pos < note_pos < branch_pos


def test_note_on_partition_follows_opening_brace() -> None:
    puml = _render(
        diagram_entities={
            "partition": [{"type": "partition", "id": "p1", "label": "Phase"}],
            "action": [{"type": "action", "id": "a1", "label": "Inside"}],
            "note": [{"id": "n1", "side": "right", "text": "Phase note"}],
        },
        diagram_connections=[_contains("p1", "a1"), _note_kc("n1", "p1")],
    )
    brace_pos = puml.index('partition "Phase" [[arch://p1]] {')
    note_pos = puml.index("note right: Phase note")
    inside_pos = puml.index(":[[arch://a1 Inside]];")
    assert brace_pos < note_pos < inside_pos


def test_empty_note_text_not_emitted() -> None:
    puml = _render(
        diagram_entities={
            "action": [{"type": "action", "id": "a1", "label": "Clean"}],
            "note": [{"id": "n1", "text": ""}],
        },
        diagram_connections=[_note_kc("n1", "a1")],
    )
    assert "note right" not in puml


def test_partition_first_lane_emitted_before_start() -> None:
    import re as _re

    puml = _render(
        diagram_entities={
            "swimlane": [{"id": "sw-1", "label": "Owner"}],
            "partition": [{"type": "partition", "id": "p1", "label": "Phase"}],
            "action": [{"type": "action", "id": "a1", "label": "Act"}],
        },
        diagram_connections=[_lane_kc("a1", "sw-1"), _contains("p1", "a1")],
    )
    start_pos = _re.search(r"^start$", puml, _re.MULTILINE).start()  # type: ignore[union-attr]
    lane_pos = puml.index("|Owner|")
    assert lane_pos < start_pos


def test_continuation_after_decision_via_step_flow() -> None:
    """After endif, step-flow on the decision leads to the continuation step."""
    puml = _render(
        diagram_entities={
            "decision": [{"type": "decision", "id": "d1", "condition": "OK?", "then_label": "yes", "else_label": "no"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Then Step"},
                {"type": "action", "id": "a2", "label": "After Decision"},
            ],
        },
        diagram_connections=[_then("d1", "a1"), _flow("d1", "a2")],
    )
    endif_pos = puml.index("endif")
    after_pos = puml.index(":[[arch://a2 After Decision]];")
    assert endif_pos < after_pos


def test_warns_at_configured_size_threshold(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="Generated PlantUML body"):
        _r(output_size_warning_threshold=10).render_body(
            "Large Flow",
            [],
            [],
            "activity",
            tmp_path,
            diagram_entities={"action": [{"type": "action", "id": "a1", "label": "Big Action"}]},
        )


def test_strip_leading_puml_frontmatter() -> None:
    puml = "---\ndiagram-entities:\n  action: []\n---\n@startuml sample\n@enduml\n"
    assert strip_leading_puml_frontmatter(puml).startswith("@startuml sample")
