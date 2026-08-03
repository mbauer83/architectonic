"""A refused write must be recognised as a refusal on every mount, whatever shape it arrives in.

`tools.mcp._answers.refusal` is the whole point of the MCP write walk. A refused write does not raise
and does not answer 4xx — it answers *normally*, with the refusal inside the success — so a harness that
checked only for an exception reads a refusal as coverage. Every gate this release added exists because
that happened.

It happened again to the harness itself, which is why this file exists. `refusal` knew two shapes and
the assurance mount uses a third: the artifact tools report ``wrote``, the viewpoint and sync tools
report ``ok``, and the assurance tools report neither — a locked store, an absent node or a rejected
field comes back as a bare ``{"error": …, "message": …}``. So the commit that started walking
`assurance-write` reported 22 tools green while one of them was refusing, and the only reason it
surfaced is that the REST route for the same operation answers 409 and the REST walk noticed.

Nothing pinned the fix, so it could have regressed to silence at any time — the failure mode of a
detector being that it detects nothing and says so cheerfully. These are the shapes, held one by one,
plus the negative cases that must *not* read as refusals: several tools on these mounts are reads in
write clothing and answer none of the three flags.
"""

from __future__ import annotations

import pytest

from tools.mcp._answers import refusal


@pytest.mark.parametrize(
    ("payload", "because"),
    [
        (
            {"wrote": False, "verification": {"issues": ["name already exists"]}},
            "the artifact tools' shape: `wrote: false` with the reason under verification",
        ),
        (
            {"wrote": False},
            "the same shape with nothing attached — still a refusal, and still worth reporting",
        ),
        (
            {"ok": False, "error": "no_upstream"},
            "the viewpoint and sync tools' shape",
        ),
        (
            {"error": "invalid_factor_assessment", "errors": [{"field": "basis_digest"}]},
            "the assurance mount's shape, which this function did not recognise until 2026-08-03",
        ),
        (
            {"error": "assurance_store_locked"},
            "a locked store, which is how every assurance tool answers when the store is not open",
        ),
        (
            {"error": "not_found", "node_id": "HAZ@1"},
            "an absent node, the other refusal an assurance write makes most often",
        ),
    ],
)
def test_a_refusal_is_recognised_whatever_shape_it_wears(
    payload: dict[str, object], because: str
) -> None:
    assert refusal(payload) is not None, because


@pytest.mark.parametrize(
    ("payload", "because"),
    [
        ({"wrote": True, "artifact_id": "APP@1"}, "a write that wrote"),
        ({"ok": True}, "a viewpoint operation that succeeded"),
        (
            {"analysis_id": "STPA@1", "node_id": "HAZ@1"},
            "an assurance write's receipt, which carries no flag at all",
        ),
        (
            {"action_required": "create_arch_entity_then_bind", "step_1": {}},
            "model-and-bind's task spec: an answer, not an error, on a path that writes nothing",
        ),
        (
            {"error": ""},
            "an empty error string is not an error; a truthiness check is what keeps this true",
        ),
        (
            {"error": None},
            "nor is an absent one, which several tools include as a null field",
        ),
        ("a string, not a mapping", "anything that is not a mapping cannot carry a flag"),
        (None, "and neither can nothing"),
    ],
)
def test_a_success_is_not_read_as_a_refusal(payload: object, because: str) -> None:
    """The other direction, and the one that would make the walk cry wolf.

    A detector that flagged successes would be switched off within a day, which is the same end state
    as one that flags nothing — so both directions are held. The `{"error": ""}` and `{"error": None}`
    cases are the specific reason the assurance branch tests truthiness rather than presence.
    """
    assert refusal(payload) is None, because
