"""What a proposed change to a promoted artifact records: one semantic edit, in a closed union.

A change against a promoted artifact is **the write call the author would have made**, recorded and
replayed later against whatever the enterprise artifact has become by then. Not a textual patch and
not a JSON patch:

* These artifacts are markdown — frontmatter, a `§content` body, a Properties table, `§display`
  blocks. Patching a parsed projection needs a canonical document-to-JSON mapping to apply and write
  back, which is a second reader of the hardest file shape this repository has, applied to content
  someone else wrote. That class of defect has cost this project three separate repairs.
* A JSON patch is positional: `/properties/3/value` means something else after an unrelated insert.
  Proposals against a moving base are the entire problem here.

Replaying the recorded call instead gets the verifier's refusal vocabulary for free and composes
with the write pipeline rather than going around it. The cost, stated: a semantic edit cannot express
every textual change — rewriting a `§content` body is a whole-field replacement. That is the same
granularity the product already offers its own authors.

**Three arms, and exactly three.** A change is proposed against a global artifact reference, and a
GAR stands for an entity, a document or a diagram. There is no connection GAR, so a connection edit
has nothing to be proposed against; connections stay a bulk-write concern unless GAR scope is
deliberately widened, which is its own decision.

**The fields are derived, never restated.** Each arm takes its vocabulary from
`edit_field_catalogue`, which is also what the MCP bulk decoder projects. Copying them here would
recreate exactly the drift the single catalogue exists to prevent — and that drift is not
hypothetical: the enterprise entity edit lost two fields that way and nothing failed.

**Mechanics are not recordable.** `rebuild_layout`, `replace_bindings` and the committed repository
a diagram resolves candidates against tell an applier how to behave. A proposal says what the
artifact should say; how a replay applies it belongs to the replay, which happens later, against
different content, possibly after a rebase.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.application.modeling.edit_field_catalogue import (
    CONTENT,
    PROPOSABLE,
    ArtifactKind,
)


class UnproposableEdit(ValueError):
    """An edit that cannot be recorded as a proposal, refused when it is proposed rather than replayed."""


@dataclass(frozen=True, slots=True)
class ProposalEdit:
    """One recorded edit: which kind of artifact, which one, and what it should say.

    Refuses to exist malformed. A field outside the kind's vocabulary is rejected here — at propose
    time, where the author is present to correct it — rather than at replay, where the failure lands
    in front of whoever is reviewing a branch.

    The vocabulary is the catalogue's `CONTENT` half, not `editable`. `editable` adds `ADDRESSING` —
    what names the subject — and the subject is already named by `artifact_id` on the edit itself. The
    two were checked separately here: the whole vocabulary, then `artifact_id` refused by name. So the
    refusal listed `artifact_id` among the accepted fields in the same sentence that rejected it.
    """

    kind: ArtifactKind
    artifact_id: str
    fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.kind not in PROPOSABLE:
            raise UnproposableEdit(
                f"{self.kind!r} cannot be proposed against: a change is addressed to a global "
                f"artifact reference, and those stand for {', '.join(PROPOSABLE)}."
            )
        if not self.artifact_id:
            raise UnproposableEdit("a proposed edit names the artifact it changes")
        unknown = sorted(set(self.fields) - CONTENT[self.kind])
        if unknown:
            raise UnproposableEdit(
                f"{unknown} {'is' if len(unknown) == 1 else 'are'} not proposable on a {self.kind}. "
                f"Accepted: {', '.join(sorted(CONTENT[self.kind]))}."
            )
        if not self.fields:
            raise UnproposableEdit("a proposed edit that changes nothing is not a change")



#: The recorded form's keys. Hyphenated to match the frontmatter vocabulary the rest of the model
#: uses, and named once so the writer and the reader cannot spell them differently.
_KIND = "kind"
_ARTIFACT_ID = "artifact-id"
_FIELDS = "fields"


def to_mapping(edit: ProposalEdit) -> dict[str, Any]:
    """The recorded form: what a change file stores, and the only thing a replay reads back."""
    return {_KIND: edit.kind, _ARTIFACT_ID: edit.artifact_id, _FIELDS: dict(edit.fields)}


def from_mapping(recorded: Mapping[str, Any]) -> ProposalEdit:
    """Read a recorded edit, refusing anything the union does not admit.

    Every refusal `ProposalEdit` makes at construction is made here too, because a file is the one
    place a malformed edit can arrive from without an author present — hand-edited, written by an
    older version, or carried across a rebase.
    """
    missing = [key for key in (_KIND, _ARTIFACT_ID, _FIELDS) if key not in recorded]
    if missing:
        raise UnproposableEdit(f"a recorded edit is missing {missing}")
    fields = recorded[_FIELDS]
    if not isinstance(fields, Mapping):
        raise UnproposableEdit(f"a recorded edit's {_FIELDS!r} is a mapping, not {type(fields).__name__}")
    return ProposalEdit(
        kind=recorded[_KIND], artifact_id=str(recorded[_ARTIFACT_ID]), fields=dict(fields)
    )
