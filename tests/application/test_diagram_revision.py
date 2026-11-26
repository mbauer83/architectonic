"""The revision a replacement is checked against: what it would overwrite unseen, in three named parts."""

from __future__ import annotations

import pytest

from src.application.modeling.diagram_revision import DiagramChanged, refuse_a_stale_replacement, replaced_revision

SOURCE = """---
artifact-id: ARC@1.a.d
name: D
status: draft
entity-ids-used:
- ACT@1.a.x
layout:
  elements:
    ACT_a: {x: 10, y: 10}
last-updated: '2026-11-01T00:00:00Z'
---
@startuml
rectangle "X" <<business_actor>> as ACT_a
@enduml
"""


def test_neither_the_layout_nor_the_stamp_moves_it() -> None:
    arranged = SOURCE.replace("{x: 10, y: 10}", "{x: 50, y: 70}").replace("2026-11-01", "2026-11-02")

    assert replaced_revision(arranged) == replaced_revision(SOURCE)


@pytest.mark.parametrize(("changed", "named"), [
    (SOURCE.replace("- ACT@1.a.x", "- ACT@1.a.x\n- ACT@1.b.y"), "what it draws"),
    (SOURCE.replace("status: draft", "status: active"), "its name, status and other statements"),
    (SOURCE.replace('"X"', '"Y"'), "its PlantUML body"),
])
def test_a_refusal_names_the_part_that_changed(changed: str, named: str) -> None:
    with pytest.raises(DiagramChanged) as refused:
        refuse_a_stale_replacement("ARC@1.a.d", read=replaced_revision(SOURCE), source=changed)

    message = str(refused.value)
    assert named in message
    assert "2026-11-01" in message
    assert refused.value.current == replaced_revision(changed)


def test_the_revision_read_is_accepted() -> None:
    refuse_a_stale_replacement("ARC@1.a.d", read=replaced_revision(SOURCE), source=SOURCE)
