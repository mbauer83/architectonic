"""The search pattern for "every reference to this entity, however it is spelled".

Used against raw file text, not against a single id, so its bounds matter more than the
validation grammar's. Two id shapes share that text: a plain full id, and a composite
connection id joining two full ids with ``---``. A slug pattern permitting runs of hyphens
matches greedily across the join, so substituting the match deletes the separator and the
prefix of the endpoint beyond it — turning ``A.slug---BBB@2.rand.slug2`` into
``A.new@2.rand.slug2``, a reference to nothing.
"""

from __future__ import annotations

from src.domain.artifact_id import full_ids_with_stem

_STEM = "DRV@1780655839.AcMaI1"
_COMPOSITE = f"{_STEM}.old-slug---ASS@1780655839.6cIRhr.other-slug@@leads-to"


class TestBounds:
    def test_a_match_stops_at_a_connection_join(self) -> None:
        assert full_ids_with_stem(_STEM).findall(_COMPOSITE) == [f"{_STEM}.old-slug"]

    def test_rewriting_a_composite_id_preserves_the_far_endpoint(self) -> None:
        rewritten = full_ids_with_stem(_STEM).sub(f"{_STEM}.new-slug", _COMPOSITE)

        assert rewritten == f"{_STEM}.new-slug---ASS@1780655839.6cIRhr.other-slug@@leads-to"

    def test_a_longer_stem_is_not_matched_by_a_shorter_one(self) -> None:
        """``@1.Ab`` must not match inside ``@1.Abc.slug``."""
        assert full_ids_with_stem("GOL@1.Ab").findall("GOL@1.Abc.some-slug") == []

    def test_a_plain_full_id_matches_whole(self) -> None:
        assert full_ids_with_stem(_STEM).sub("X", f"{_STEM}.old-slug") == "X"

    def test_a_multi_hyphen_slug_does_not_extend_past_its_own_id(self) -> None:
        text = f"{_STEM}.a-b-c-d---ASS@1.rand.z"

        assert full_ids_with_stem(_STEM).findall(text) == [f"{_STEM}.a-b-c-d"]

    def test_the_short_form_alone_is_not_matched(self) -> None:
        """A reference already in stable form has no slug to repair."""
        assert full_ids_with_stem(_STEM).findall(f"{_STEM} and more") == []
