"""The group-operation contract, held against the six returns it projects.

The second instance of one lesson. `DocumentReference` was written from a guess — `artifact_id` where
the producer emits `document_id` — and being closed it rejected every real response, so
`GET /api/entities/{id}` answered 500 for any entity a document cited. A field-set comparison against
the producer is what turns "derives from the use-case output" from a claim in a docstring into
something that fails when it stops being true.

`group_ops` returns six shapes, one per action. Their union is the DTO's field set, and no member may
be absent from it or invented by it.
"""

from __future__ import annotations

import ast
import pathlib

from src.infrastructure.gui.contracts.groups import GroupOperationResponse

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


def test_the_dto_declares_every_field_the_producer_can_emit() -> None:
    """A key the producer emits and the DTO does not is a rejected response — the model is closed."""
    declared = set(GroupOperationResponse.model_fields)
    emitted = set().union(*_returned_key_sets())
    assert emitted <= declared, f"producer emits fields the contract omits: {sorted(emitted - declared)}"


def test_the_dto_invents_no_field_the_producer_never_emits() -> None:
    """The other direction. A field no producer sets is either dead or a rename in disguise, and a
    rename is what made the entity read answer 500."""
    declared = set(GroupOperationResponse.model_fields)
    emitted = set().union(*_returned_key_sets())
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
