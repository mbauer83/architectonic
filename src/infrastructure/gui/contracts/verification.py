"""The validity report a mutation returns alongside what it wrote.

``WriteResult.verification`` is a ``dict[str, Any]`` in the write layer, and the delivery DTO
mirrored that type verbatim — so ``WriteResultResponse``, a model whose own docstring says it is
closed, published ``additionalProperties: true`` for this one field on *every* mutation response.
A client reading the schema learned that a write returns "an object" where the write layer has
emitted the same four keys throughout: ``path``, ``file_type``, ``valid``, ``issues``.

The severity and file-type vocabularies are the verifier's own
(:mod:`src.application.verification.artifact_verifier_types`) rather than re-spelled here. A rule
that gains a severity should widen the published schema, and it does: the generated document
changes, `npm run contracts:check` reports the committed types stale, and the widening is reviewed
instead of being invisible on one side of the boundary.

``path`` and ``file_type`` are optional because several producers omit them for a write that
never reached a file — a refused duplicate, a dry run over a diagram that does not exist yet
(``artifact_write/document.py:345``, ``admin_diagram_ops.py:60``). ``location`` is optional for the
same reason: an issue about the artifact as a whole has no line to point at.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from src.application.verification.artifact_verifier_types import (
    SeverityLiteral,
    VerificationFileType,
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssuranceVerificationFinding(_Closed):
    """One finding from the verify that runs after a write.

    Advisory, always: a write is never blocked by the verifier, so a finding here reports on a
    change that has already happened. ``node_id`` is null for a finding about the store as a whole
    rather than one node — the scoping filter reads it, and a client grouping by node has to too.
    """

    severity: str
    code: str
    message: str
    node_id: str | None


class VerificationIssueResponse(_Closed):
    """One finding: what is wrong, how badly, and where.

    ``details`` and ``actions`` stay open maps, and they are the only two levels here that may be
    (see ``contracts/open_models.py``): both are written by the *rule* that raised the issue, and
    rules live in the core verifier and in diagram-type modules alike — the datatype module's
    unresolved-type-reference finding carries ``classifier``/``attr_name``/``candidates``
    (``diagram_types/datatype/_contributions.py:140``), and the workspace-identity rule carries
    ``candidate_host``/``committed_host``. Enumerating either here would make a module's findings
    depend on this package to reach a client.
    """

    severity: SeverityLiteral
    code: str
    message: str
    location: str | None = None
    details: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None


class WriteVerificationResponse(_Closed):
    """Whether what the mutation wrote verifies, and what it found if not.

    Not an error channel: a write that failed raises and answers non-2xx. ``valid`` false with the
    issues that made it so is a *successful* write of content the verifier objects to, which is why
    the authoring surfaces render these as warnings beside the saved artifact rather than as a
    failure.
    """

    path: str | None = None
    file_type: VerificationFileType | None = None
    valid: bool
    issues: list[VerificationIssueResponse] = []
