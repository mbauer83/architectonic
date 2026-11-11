"""An activity diagram holding diagram-only records, for tests of how held records are addressed.

The note holds no relations, so no reference blocks a write addressed to it — the shape that let an
entity delete reach the host diagram (B109).
"""

from __future__ import annotations

from pathlib import Path

DIAGRAM_ID = "ACT@1234567890.aBcDeF.my-process"
NOTE_ID = f"{DIAGRAM_ID}#note/n1"
ACTION_ID = f"{DIAGRAM_ID}#action/a1"

DIAGRAM = f"""\
---
artifact-id: {DIAGRAM_ID}
artifact-type: diagram
name: "My Process"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-05-09'
diagram-entities:
  swimlane:
    - id: sw-1
      label: Customer
  action:
    - id: a1
      label: Submit Form
      lane_id: sw-1
  note:
    - id: n1
      text: Attached annotation
      side: right
---
@startuml my-process
title My Process
@enduml
"""


def repository_with_held_records(tmp_path: Path, engagement: str) -> Path:
    """An engagement repository whose only content is the diagram above."""
    root = tmp_path / "engagements" / engagement / "architecture-repository"
    (root / "model").mkdir(parents=True)
    diagram_file(root).parent.mkdir(parents=True)
    diagram_file(root).write_text(DIAGRAM, encoding="utf-8")
    return root


def diagram_file(root: Path) -> Path:
    return root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml"
