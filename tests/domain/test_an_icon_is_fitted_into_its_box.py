"""An icon is fitted into the room it is given, keeping its shape, so no aspect ratio shrinks to a strip."""

from __future__ import annotations

import pytest

from src.domain.icons.render_form import STORED_BOX, IconBox

BADGE = IconBox(height_px=20, max_width_px=60)


@pytest.mark.parametrize(
    ("width", "height", "drawn"),
    [(128, 128, (20, 20)), (384, 96, (60, 15)), (256, 128, (40, 20)), (43, 128, (7, 20))],
    ids=["square", "wordmark, width-bound", "2:1, height-bound", "tall, height-bound"],
)
def test_a_picture_takes_the_boxes_height_unless_it_would_run_too_wide(
    width: int, height: int, drawn: tuple[int, int]
) -> None:
    scale = BADGE.scale_for(width, height)

    assert (round(width * scale), round(height * scale)) == drawn


def test_the_stored_box_holds_what_fits_and_nothing_larger() -> None:
    assert STORED_BOX.holds(384, 128) and STORED_BOX.holds(128, 128)
    assert not STORED_BOX.holds(385, 10) and not STORED_BOX.holds(10, 129)


def test_every_icon_stored_before_the_box_still_fits_it() -> None:
    """Icons were stored at most 128 px on either edge; those files stay valid."""
    assert STORED_BOX.holds(128, 128) and STORED_BOX.holds(128, 32) and STORED_BOX.holds(32, 128)
