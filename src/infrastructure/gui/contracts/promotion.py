"""Response contracts for promotion: the plan, and the result of carrying it out.

Promotion copies engagement artifacts into the enterprise repository, so the *plan* is the thing a
person reads before agreeing to it — every list on it is a question they have to answer. That is why
none of them are optional here: a plan that omits a key when it is empty makes "nothing conflicts" and
"conflicts not computed" the same reply, and the client's own decoder had four of them optional and two
missing outright.

Derived from ``promote_to_enterprise.plan_promotion`` and the two branches of ``promotion_execute``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromotionEntityConflict(_Closed):
    """An entity that exists in both repositories, with both readings side by side.

    ``engagement_fields`` and ``enterprise_fields`` are the two versions' frontmatter, published so the
    resolution UI can show a field-by-field diff and offer a merge — which is the whole point of
    surfacing a conflict rather than refusing the promotion.
    """

    engagement_id: str
    enterprise_id: str
    artifact_type: str
    engagement_name: str
    enterprise_name: str
    engagement_fields: dict[str, Any]
    enterprise_fields: dict[str, Any]


class PromotionDocumentConflict(_Closed):
    """A document that exists in both repositories."""

    engagement_id: str
    enterprise_id: str
    doc_type: str
    engagement_title: str
    enterprise_title: str


class PromotionDiagramConflict(_Closed):
    """A diagram that exists in both repositories."""

    engagement_id: str
    enterprise_id: str
    diagram_type: str
    engagement_name: str
    enterprise_name: str


class PromotionGroupMappingEntry(_Closed):
    """Where one engagement group lands in the enterprise repository.

    ``match_status`` is the decision: matched by id, a conflicting slug, or new. ``enterprise_group_id``
    is null for ``new`` — there is nothing to point at yet.
    """

    engagement_slug: str
    engagement_group_id: str
    match_status: Literal["matched_by_id", "conflict", "new"]
    enterprise_slug: str
    enterprise_group_id: str | None


class EnterpriseGroupOption(_Closed):
    """One enterprise group a mapping may be redirected to."""

    slug: str
    id: str
    name: str


class StructuralClosureEntity(_Closed):
    """One entity missing from the selection."""

    artifact_id: str
    name: str
    artifact_type: str


class StructuralClosureRequirement(_Closed):
    """A selected junction or grouping whose meaning-carrying entities are not in the selection.

    A junction promoted without what it joins is a structure that means nothing at the far end, so the
    entities are named rather than the promotion being refused: the GUI offers "include the missing
    entities" from exactly this data.
    """

    entity_id: str
    entity_name: str
    kind: Literal["junction", "grouping"]
    missing: list[StructuralClosureEntity]


class PromotionViewpointDependency(_Closed):
    """A viewpoint a promoted diagram or matrix is pinned to, and where it stands enterprise-side.

    ``enterprise_version`` is null when the viewpoint is not there at all — which is the case that
    forces a choice between promoting it alongside and repinning, and the reason this list exists.
    """

    target_id: str
    target_kind: str
    slug: str
    pinned_version: str
    status: str
    enterprise_version: str | None


class PromotionMissingDependency(_Closed):
    """An artifact the selection references but does not include, and what needs it."""

    artifact_id: str
    name: str
    record_type: str
    required_by: str
    kind: str


class PromotionPlanResponse(_Closed):
    """What a promotion would do, and every question it raises before it may proceed.

    Nothing here is optional. Four of these lists were optional in the client's decoder and two were
    absent from it — ``viewpoint_dependencies`` and ``missing_dependencies``, which are the two that
    can make a promotion produce a broken enterprise repository. An empty list and an uncomputed one
    have to be distinguishable, and only one of them is representable when the key may be missing.
    """

    entity_id: str
    entities_to_add: list[str]
    conflicts: list[PromotionEntityConflict]
    connection_ids: list[str]
    already_in_enterprise: list[str]
    documents_to_add: list[str]
    diagrams_to_add: list[str]
    doc_conflicts: list[PromotionDocumentConflict]
    diagram_conflicts: list[PromotionDiagramConflict]
    warnings: list[str]
    schema_errors: list[str]
    structural_closure: list[StructuralClosureRequirement]
    group_mapping: list[PromotionGroupMappingEntry]
    available_enterprise_groups: list[EnterpriseGroupOption]
    viewpoint_dependencies: list[PromotionViewpointDependency]
    missing_dependencies: list[PromotionMissingDependency]


class PromotionResultResponse(_Closed):
    """What carrying out the plan actually did.

    ``dry_run`` and ``executed`` are both stated because they answer different questions: a dry run
    never executes, but an execution can also fail to, and a caller distinguishing "we did not try"
    from "we tried and stopped" needs both.

    ``rolled_back`` is the one to read after a failure. The promotion runs in a git worktree
    transaction, so a verification error leaves the enterprise repository as it was — and saying so is
    what stops an operator from going to clean up by hand.

    ``warnings`` carries the plan's, which the dry-run branch does not currently populate; the key is
    always present so a reader never has to tell an absent list from an empty one.
    """

    dry_run: bool
    executed: bool
    copied_files: list[str]
    updated_files: list[str]
    verification_errors: list[str]
    rolled_back: bool
    warnings: list[str] = []
