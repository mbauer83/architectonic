"""The group-operation contract, held against the six returns it projects.

The second instance of one lesson. `DocumentReference` was written from a guess — `artifact_id` where
the producer emits `document_id` — and being closed it rejected every real response, so
`GET /api/entities/{id}` answered 500 for any entity a document cited. A field-set comparison against
the producer is what turns "derives from the use-case output" from a claim in a docstring into
something that fails when it stops being true.

`group_ops` returns six shapes, one per action. Their union is the DTO's field set, and no member may
be absent from it or invented by it.

**A seventh shape hid behind that sentence for a release.** Deleting a *model-project* does not go
through `group_ops`' own delete — it delegates to `cascade_delete_model_project` in another module,
which answers in its own envelope with no `action` at all. This file scanned one module for returns
containing `action`, so the one shape that broke the contract was the one shape it structurally could
not see, and every model-project deletion through REST answered 500 until a write walk requested the
route. The producer set below now includes the router's projection of that envelope, obtained by
*calling* it rather than by restating its keys.
"""

from __future__ import annotations

import ast
import pathlib

from src.infrastructure.rest.contracts.groups import GroupOperationResponse

_GROUP_OPS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src" / "infrastructure" / "write" / "artifact_write" / "group_ops.py"
)


def _returned_key_sets() -> list[frozenset[str]]:
    """Every ``return {...}`` literal in `group_ops`, as its set of keys.

    Read from the source rather than by calling the six functions: each needs a repository on disk in
    a particular state, and the question here is about the shapes the module *can* return, which is a
    property of the code and not of any one fixture.
    """
    tree = ast.parse(_GROUP_OPS.read_text(encoding="utf-8"))
    shapes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # Only the operation summaries, which every one of them identifies with `action`.
        if "action" in keys:
            shapes.append(frozenset(keys))
    return shapes


def test_the_producer_returns_the_six_shapes_this_contract_projects() -> None:
    """Guards the guard: if the extraction found nothing, every assertion below would hold vacuously."""
    shapes = _returned_key_sets()
    assert len(shapes) == 6, f"expected one summary per action, found {len(shapes)}"


#: A cascade report as `cascade_delete_model_project` answers one, used to obtain the projected shape.
#: Values are irrelevant here — only the keys are — but they are realistic so the DTO validation below
#: is meaningful rather than vacuous.
_CASCADE_REPORT = {
    "project": "payments",
    "dry_run": False,
    "applied": True,
    "staged_paths": [".arch-repo/groups.yaml"],
    "warnings": ["one diagram could not be rewritten"],
    "owned_deleted": 4,
    "foreign_connections_deleted": 2,
    "diagrams_updated": 1,
}


def _projected_delete_keys() -> frozenset[str]:
    """What the router hands the DTO for a model-project delete, by calling the projection."""
    from src.infrastructure.rest.routers.groups import project_group_delete

    return frozenset(project_group_delete(dict(_CASCADE_REPORT), axis="model-project", slug="payments"))


def test_the_dto_declares_every_field_the_producer_can_emit() -> None:
    """A key the producer emits and the DTO does not is a rejected response — the model is closed."""
    declared = set(GroupOperationResponse.model_fields)
    emitted = set().union(*_returned_key_sets()) | _projected_delete_keys()
    assert emitted <= declared, f"producer emits fields the contract omits: {sorted(emitted - declared)}"


def test_the_dto_invents_no_field_the_producer_never_emits() -> None:
    """The other direction. A field no producer sets is either dead or a rename in disguise, and a
    rename is what made the entity read answer 500."""
    declared = set(GroupOperationResponse.model_fields)
    emitted = set().union(*_returned_key_sets()) | _projected_delete_keys()
    assert declared <= emitted, f"contract declares fields nothing produces: {sorted(declared - emitted)}"


def test_the_fields_common_to_every_action_are_required() -> None:
    """What every shape carries is what a client may rely on unconditionally; the rest is optional."""
    always = frozenset.intersection(*_returned_key_sets())
    required = {
        name for name, field in GroupOperationResponse.model_fields.items() if field.is_required()
    }
    assert required == always, f"required={sorted(required)} but every action emits {sorted(always)}"


def test_every_action_the_producer_reports_is_a_permitted_value() -> None:
    """`action` is a closed literal, so a seventh operation added to the producer without a value here
    would fail its own response rather than shipping an undocumented verb."""
    tree = ast.parse(_GROUP_OPS.read_text(encoding="utf-8"))
    reported = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=False):
            if isinstance(key, ast.Constant) and key.value == "action" and isinstance(value, ast.Constant):
                reported.add(value.value)
    permitted = set(GroupOperationResponse.model_fields["action"].annotation.__args__)  # type: ignore[union-attr]
    assert reported == permitted, f"producer reports {sorted(reported)}, contract permits {sorted(permitted)}"


def test_a_real_summary_from_each_action_validates() -> None:
    """The field sets agreeing is necessary, not sufficient: the *types* have to agree too."""
    for summary in (
        {"action": "created", "axis": "model-project", "slug": "platform", "id": "grp-1"},
        {"action": "renamed", "axis": "docs", "slug": "new", "old_slug": "old"},
        {"action": "archived", "axis": "docs", "slug": "old"},
        {"action": "unarchived", "axis": "docs", "slug": "old"},
        {"action": "updated", "axis": "diagram-catalog", "slug": "views"},
        {"action": "deleted", "axis": "docs", "slug": "gone", "files_removed": 0},
    ):
        validated = GroupOperationResponse.model_validate(summary)
        assert validated.action == summary["action"]

    # Zero removals is a real outcome, and must survive as zero rather than being confused with
    # "not applicable" — which is why the unset extras are absent rather than null.
    deleted = GroupOperationResponse.model_validate(
        {"action": "deleted", "axis": "docs", "slug": "gone", "files_removed": 0}
    )
    assert deleted.model_dump(exclude_none=True)["files_removed"] == 0


def test_a_projected_cascade_report_validates_against_the_contract() -> None:
    """The regression. Returned verbatim, this envelope was eleven validation errors and a 500.

    Watched fail without the projection: three required fields missing (`action`, `axis`, `slug`) and
    eight extras forbidden. Validating the projection rather than asserting its keys, because what broke
    was the *model rejecting the body* — the same failure mode either way, checked the way it happens.
    """
    from src.infrastructure.rest.routers.groups import project_group_delete

    projected = project_group_delete(dict(_CASCADE_REPORT), axis="model-project", slug="payments")
    response = GroupOperationResponse.model_validate(projected)

    assert response.action == "deleted"
    assert response.slug == "payments"
    # The cascade's own facts survive: a caller has to be able to learn that a neighbouring project's
    # diagram changed under it, which is the whole reason these fields are on the wire.
    assert response.owned_deleted == 4
    assert response.foreign_connections_deleted == 2
    assert response.diagrams_updated == 1
    assert response.warnings == ["one diagram could not be rewritten"]


def test_the_projection_leaves_a_normal_group_result_alone() -> None:
    """Five of the six actions already answer in the contract's shape; the projection must not touch
    them, or a rename would start reporting itself as a delete."""
    from src.infrastructure.rest.routers.groups import project_group_delete

    already = {"action": "deleted", "axis": "diagram-collection", "slug": "views", "files_removed": 3}
    assert project_group_delete(dict(already), axis="diagram-collection", slug="views") == already


def test_a_cascade_that_deleted_nothing_reports_zero_rather_than_absence() -> None:
    """Zero is an outcome; absence means "no cascade ran". The null-omitting policy makes those two
    indistinguishable if the projection drops a zero, so it must not."""
    from src.infrastructure.rest.routers.groups import project_group_delete

    empty = {"project": "empty", "warnings": [], "owned_deleted": 0,
             "foreign_connections_deleted": 0, "diagrams_updated": 0}
    projected = project_group_delete(empty, axis="model-project", slug="empty")
    assert projected["owned_deleted"] == 0
    assert GroupOperationResponse.model_validate(projected).owned_deleted == 0
