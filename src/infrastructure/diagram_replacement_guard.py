"""What must hold of a stored diagram before a replacement writes over it whole.

Two things, asked of the file as it is when the write queue reaches the replacement, so what is checked is
what is written over: that it is still the diagram the caller read (`diagram_revision`), and that its body
is the generator's to write again, unless the replacement gives a hand-written one up
(`diagram_body_ownership`). Kept beside the replacement rather than inside it, as one call, so the save
reads as what it writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.application.modeling.diagram_revision import refuse_a_stale_replacement
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.diagram_body_ownership import refuse_a_hand_written_body
from src.infrastructure.diagram_composition import DiagramNotStored, DiagramReplacement


def refuse_an_unsafe_replacement(
    artifact_id: str, body: DiagramReplacement, *, repo: Any, repo_root: Path, catalogs: RuntimeCatalogs,
) -> None:
    """Raise where *body* may not replace *artifact_id* whole: `DiagramNotStored`, `DiagramChanged` or
    `BodyWrittenByHand`."""
    record = repo.get_diagram(artifact_id)
    if record is None or not Path(record.path).exists():
        raise DiagramNotStored(f"Diagram '{artifact_id}' not found")
    stored = Path(record.path).read_text(encoding="utf-8")
    if body.base_revision is not None:
        refuse_a_stale_replacement(artifact_id, read=body.base_revision, source=stored)
    if body.manual_layout is not False:
        refuse_a_hand_written_body(
            artifact_id, source=stored, repo=repo, repo_root=repo_root, diagram_types=catalogs.diagram_types,
        )
