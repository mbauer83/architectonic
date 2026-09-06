"""The vocabulary of a proposed change to a promoted artifact: its type, its fields, its states.

A proposed change is an artifact in the engagement repository that says: *this promoted artifact
should say something different*. It is system-managed like a global artifact reference — created by
the propose operation, never authored directly — and carries four things and no more:

* **what it is about** — the global artifact reference standing for the promoted artifact. Not the
  enterprise artifact's own id: a non-admin deployment holds no enterprise content, and the GAR is
  the thing it can point at.
* **the recorded edit** — one `ProposalEdit`, the write call the author would have made.
* **the base revision** — what the enterprise artifact was when the change was written. A change
  whose base has moved is stale, which is a condition to report and not a broken state.
* **its state** — where it is in its own lifecycle.

**Declared once, here, because both the writer and the verifier need it and they sit on opposite
sides of the layering.** The verifier is application code and may not import the infrastructure that
writes these files, so a key declared beside the writer would have to be spelled again beside the
rule. That is not hypothetical: `global-artifact-id` was spelled at eight sites under four constant
names before `enterprise_reference.py` gave it one owner, and the copies had drifted — the index
bucketed a reference under its stripped target while the duplicate check compared the raw value. This
module is the same shape, written that way from the start.

**`rejected` is not a state.** Nothing could enter it: there is no reject operation, and the reviewer
works in the enterprise repository with no account on this deployment. A rejection reaches the author
out of band, and recording one would be self-reported evidence — a different design with its own
operation. Absence of a remote branch is not rejection either: it is equally consistent with reviewer
deletion, withdrawal elsewhere, revoked permission, or an unreachable remote.

**`stale` and `conflicting` are not states either.** They are computed from the base revision against
the enterprise repository at the moment someone asks, and storing them would mean a file that claims
to know something it cannot.
"""

from __future__ import annotations

from typing import Literal, get_args

#: The entity type a proposed change is stored as. Internal, like a global artifact reference:
#: system-managed, and never offered in a user-facing entity list.
PROPOSED_CHANGE_TYPE = "proposed-change"

#: The global artifact reference this change is about.
PROPOSES_CHANGE_TO = "proposes-change-to"

#: The recorded edit, as `proposal_edit.to_mapping` writes it.
RECORDED_EDIT = "recorded-edit"

#: What the enterprise artifact was when the change was written.
BASE_REVISION = "base-revision"

#: Where the change is in its lifecycle.
PROPOSAL_STATE = "proposal-state"

#: What `base-revision` says when the enterprise artifact could not be read at the moment the change
#: was written — the ordinary state of an engagement deployment, which mounts no enterprise content.
#: A value rather than an empty field because the field may not be empty (E148) and a change nothing
#: can decode is a change nobody can see: recording the blank made the whole feature fail on the
#: deployment shape it exists for. Staleness is then undecidable, which reads as `current` for the
#: same reason a missing revision does — the check that matters happens at review, where both sides
#: are visible.
UNKNOWN_BASE = "unknown"

#: The lifecycle. `draft` and `submitted` are live; `integrated` and `abandoned` are terminal and
#: immutable — a terminal record is kept rather than deleted, because it is the evidence that the
#: proposal existed and how it ended. Which states are terminal is declared where the transition
#: rule enforces it, not here: a constant nothing consults is a claim nothing checks.
ProposalState = Literal["draft", "submitted", "integrated", "abandoned"]

STATES: tuple[str, ...] = get_args(ProposalState)

#: The states in which a change still makes its target differ from the enterprise baseline. An
#: integrated change *is* the baseline now, and an abandoned one never will be, so neither is a local
#: difference a reader needs told about. Declared here rather than beside the resolver because the
#: same partition decides what a transition may leave, and two spellings of it would drift.
PENDING_STATES: frozenset[str] = frozenset({"draft", "submitted"})
