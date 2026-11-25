"""*Save as diagram*: the generated view a candidate is drawn on, stored as a diagram the candidate is then drawn on.

A candidate whose stack names no stored diagram is drawn as a view generated from its scope (Q36): from a
search, a viewpoint no stored diagram applies, or an empty start. That view is computed on every read and
has no layout of its own to keep, and the canvas a candidate is sketched on is a stored diagram's. Saving
it writes a new diagram through the one write path — the same composition the view is drawn from
(`generated_composition`), the same create every diagram goes through — and names it as the diagram the
candidate is drawn on.

**What the diagram holds is the model's, never the candidate's.** It draws the entities of the scope the
model holds and the relations among them, as the generated view does. What the candidate creates, renames
or connects stays in its operations and reaches the model only when it is applied; the canvas draws it over
the saved diagram as it does over any stored one. So saving is an explicit write of a view of the current
model, made by its author, and nothing of the candidate is written by it. A candidate whose scope holds
nothing the model has (an empty start) has no view to save, and is refused: an ArchiMate diagram that draws
nothing is not a diagram the verifier accepts (E303).

The diagram is written first and the candidate named after it: the candidate store lies outside the write
path's transaction, as it does for an apply. If the candidate changed meanwhile, the diagram stays — a view
of the model, correct whether or not anything is drawn on it — and the refusal names it, to be chosen.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

from src.application.artifacts.repository import ArtifactRepository
from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_apply import TERMINAL
from src.application.change_sets.candidate_recorded_form import to_mapping
from src.application.change_sets.stacking import drawn_on, stack_of
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.candidates.repository import CandidateConflict
from src.infrastructure.candidates.scope_drawing import generated_composition
from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.diagram_composition import DiagramComposition
from src.infrastructure.diagram_creation import DiagramFiling, create_composed_diagram
from src.infrastructure.write.artifact_write.types import WriteResult

#: A new diagram written from a composition, bound by the transport to its verifier: the composition, the
#: collection it is filed in, dry run.
DiagramWriter: TypeAlias = Callable[[DiagramComposition, str, bool], WriteResult]


def save_as_diagram(
    service: CandidateService, ref: str, write: DiagramWriter, *, based_on: str, name: str | None = None,
    group: str | None = None, dry_run: bool,
) -> dict[str, Any]:
    """Write the view *ref* is drawn on as a new diagram named *name* (the candidate's own name when absent),
    filed in *group*, and draw *ref* on it. A dry run answers what would be written and writes nothing."""
    candidate = service.store.require(ref)
    version = record_revision(to_mapping(candidate))
    if based_on != version:
        raise CandidateConflict(f"The candidate changed: its current version is {version}. Read it before saving.")
    if candidate.state in TERMINAL:
        raise CandidateConflict(f"{candidate.id} is {candidate.state}, which is final; it is drawn as it was.")
    stack = stack_of(candidate, service.store.find)
    if (stored := drawn_on(stack)) is not None:
        raise CandidateConflict(
            f"{candidate.id} is drawn on the stored diagram {stored} already. Save as diagram stores the view a "
            "candidate drawn on no stored diagram is generated as."
        )
    body = generated_composition(
        ArtifactRepository(service.index), [one for layer in stack for one in layer.scope], name or candidate.name,
    )
    if not body.entity_ids:
        raise ValueError(
            f"{candidate.id} reads over nothing the model holds, so there is no view to save as a diagram. Draw it "
            "on a stored diagram instead, or give it a scope."
        )
    written = write(body, group or UNCATEGORIZED, dry_run)
    if written.error_messages or written.wrote == dry_run:
        said = " ".join(written.error_messages) or "it was refused"
        raise ValueError(f"The diagram cannot be {'planned' if dry_run else 'written'}: {said}")
    answer = {
        "candidate": candidate.id, "dry_run": dry_run, "diagram": None if dry_run else written.artifact_id,
        "name": body.name, "entities": len(body.entity_ids), "relations": len(body.connection_ids),
    }
    if dry_run:
        return answer
    try:
        saved = service.save(to_mapping(candidate) | {"diagram": written.artifact_id}, version, ref=candidate.id)
    except CandidateConflict as conflict:
        raise CandidateConflict(
            f"The diagram {written.artifact_id} was written, but {candidate.id} changed meanwhile and is not "
            f"drawn on it yet: choose {written.artifact_id} as the diagram it is drawn on. ({conflict})"
        ) from conflict
    return answer | {"version": saved["version"]}


def diagram_writer(
    repo: Any, repo_root: Path, verifier: ArtifactVerifier, clear_caches: Callable[[Path], None],
) -> DiagramWriter:
    """A new diagram written as every diagram is created, by the transport's verifier."""

    def write(body: DiagramComposition, group: str, dry_run: bool) -> WriteResult:
        return create_composed_diagram(
            body, DiagramFiling(group=group), repo=repo, repo_root=repo_root, verifier=verifier,
            clear_caches=clear_caches, dry_run=dry_run,
        )

    return write
