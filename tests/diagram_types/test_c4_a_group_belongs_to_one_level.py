"""A C4 group is drawn on the view whose root is its parent, and not on the level above.

Recorded as a defect — *a C4 group draws flat where its members sit a level deeper* — with a proposed
fix: roll a grouping up so that a group whose members all lie inside one drawn container becomes a
nested boundary within it. Measured against the shipped model before building any of that, and the
proposal does not survive the measurement:

* All five groupings under `APP@1777293133.OYEmP1` have **every** member rolling up to that one
  container. None spans containers, so the "boundary around several containers" branch has no
  instance, and the other branch would draw five empty labelled boxes inside one box.
* The mechanism blamed is not reached. `groupings_without_members` never sees them: `internal_ids` is
  built from `_structural_children(root, 1)`, and a grouping whose structural parent is the backend is
  not a child of the *platform*, so it is out before membership is consulted.

What the behaviour actually is: a group is drawn where its parent is the view's root, holding the
members that level draws. That is C4's own rule — a group holds elements of one abstraction level —
and a container view showing a container's internal groupings would be mixing two.

So this pins the rule rather than changing it. What a reader loses at the container level is real, and
the answer is the component view, which is where these five are drawn with their members inside.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.diagram_types.c4._projection import project_c4
from src.diagram_types.c4._projection_rollup import descendants
from src.diagram_types.c4._projection_vocabulary import GROUPING_TYPE, NESTING_TYPES, entity_type

PLATFORM = "APP@1780783671.hkrdtm.architecture-management-platform"
BACKEND = "APP@1777293133.OYEmP1.architecture-backend"


@lru_cache(maxsize=1)
def _query():
    from src.infrastructure.artifact_index import shared_artifact_index

    root = Path("engagements/ENG-ARCH-REPO/architecture-repository").resolve()
    if not root.exists():  # pragma: no cover - the repository is present in this checkout
        pytest.skip("engagement repository not available")
    return shared_artifact_index([root])


def _project(diagram_type: str, root: str):
    return project_c4(
        diagram_type, root, _query(),
        internal_c4_type="container", scope_entity_type="software-system",
        person_archimate_types=frozenset(),
    )


def _groupings_drawn(projection) -> list[str]:
    return [i.entity_id for i in projection.items if entity_type(i.entity_id, _query()) == GROUPING_TYPE]


class TestAGroupIsDrawnWhereItsParentIsTheRoot:
    def test_the_component_view_draws_the_backend_groupings(self) -> None:
        """Not an exact count: authoring another concern group is the product working."""
        drawn = _groupings_drawn(_project("c4-component", BACKEND))

        assert drawn, "the backend's groupings belong on its component view"

    def test_each_one_holds_the_members_that_level_draws(self) -> None:
        projection = _project("c4-component", BACKEND)
        held = {parent for _child, parent in projection.contained_by}

        for group_id in _groupings_drawn(projection):
            assert group_id in held, f"{group_id} is drawn as a boundary around nothing"

    def test_the_level_above_draws_none_of_them(self) -> None:
        """The container view of the platform draws the backend as one box. Its groupings are one
        level down, and a group holds elements of one level."""
        assert _groupings_drawn(_project("c4-container", PLATFORM)) == []


class TestWhyTheProposedRollUpWasNotBuilt:
    def test_no_grouping_spans_two_containers(self) -> None:
        """The branch a roll-up would exist for. Stated as a property of the model rather than a
        count, so authoring a grouping that *does* span containers fails here and reopens the
        question with a live case to design against — which is what was missing.
        """
        query = _query()
        containers = descendants(PLATFORM, query, nesting_types=NESTING_TYPES, max_depth=1)
        spanning = []
        for group_id in (e for e in query.entity_ids() if entity_type(e, query) == GROUPING_TYPE):
            members = descendants(group_id, query, nesting_types=NESTING_TYPES, max_depth=1) - {group_id}
            homes = {
                c for c in containers
                for m in members
                if m in descendants(c, query, nesting_types=NESTING_TYPES, max_depth=6) | {c}
            }
            if len(homes) > 1:
                spanning.append((group_id, sorted(homes)))

        assert spanning == [], (
            "a grouping now spans containers, so the container level has something true to say about "
            f"it and the roll-up is worth designing: {spanning}"
        )
