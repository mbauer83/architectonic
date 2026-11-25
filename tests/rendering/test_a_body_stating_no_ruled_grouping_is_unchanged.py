"""A diagram that states no ruled grouping is drawn exactly as it was before groupings could be ruled.

Byte for byte, against bodies kept from the revision before the change: the generated text of every
scene in `tests.support.archimate_scenes`, written by running that module against that revision.
The claim is about *text*, because a body that differs in one hidden chain is a picture GraphViz may
lay out differently, and every stored diagram would then move on its next sync.

A scene added later has no kept body and fails here until one is written — by the generator as it
then stands, which is what "unchanged" will mean from that point on.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from src.domain.diagrams.authored_groupings import states_a_ruled_grouping
from src.infrastructure.rendering.diagram_builder import generate_puml_body
from tests.support.archimate_scenes import DIAGRAM_TYPE, SCENES, Scene

_KEPT = Path(__file__).parent.parent / "fixtures" / "archimate_bodies"


def body_of(scene: Scene) -> str:
    with warnings.catch_warnings():
        # The largest scene is past the size the generator warns at, which is why it is a scene.
        warnings.simplefilter("ignore", UserWarning)
        return generate_puml_body(
            scene.name, list(scene.entities), list(scene.connections), diagram_type=DIAGRAM_TYPE,
            **scene.statements,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("scene", SCENES, ids=lambda scene: scene.slug)
def test_the_body_is_the_one_kept_from_before(scene: Scene) -> None:
    assert not states_a_ruled_grouping(scene.statements.get("authored_groupings"))

    assert body_of(scene) == (_KEPT / f"{scene.slug}.puml").read_text(encoding="utf-8")


def test_every_kept_body_belongs_to_a_scene() -> None:
    assert {path.stem for path in _KEPT.glob("*.puml")} == {scene.slug for scene in SCENES}
