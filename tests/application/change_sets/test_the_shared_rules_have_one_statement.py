"""What a change set shares with the rest of the product is shared, not copied.

Three things existed before the change set and are asked by it too: which fields an edit is made of,
whether a value has moved since it was read, and what the revision of a piece of content is. Each
test here holds the change set to the existing owner — and the existing consumer to the same one.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src.application.change_sets.base import BaseRevision, BaseValue, has_moved, prose_revision
from src.application.change_sets.operations import ConnectionAddress
from src.application.derivation.refresh import compute_revision
from src.application.modeling import integration_detection
from src.application.modeling.claim_overlap import contested
from src.application.modeling.edit_field_catalogue import (
    ADDRESSING,
    CONTENT,
    CREATION,
    IN_A_CHANGE_SET,
    KEYED,
    PROPOSABLE,
    PROSE,
    atomic,
    creatable,
)
from src.application.modeling.integration_detection import fields_moved_upstream, moved_since
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.content_revision import content_revision


class TestTheCatalogueSaysHowAFieldIsAddressed:
    @pytest.mark.parametrize("kind", sorted(CONTENT))
    def test_every_field_is_addressed_exactly_one_way(self, kind: str) -> None:
        """Keyed, prose or atomic — a field in two classes would have two meanings of one edit."""
        classes = (KEYED[kind], PROSE[kind], atomic(kind))  # type: ignore[index, arg-type]
        assert set().union(*classes) == CONTENT[kind]  # type: ignore[index]
        assert sum(len(fields) for fields in classes) == len(CONTENT[kind])  # type: ignore[index]

    def test_the_keyed_fields_are_the_ones_the_write_path_patches(self) -> None:
        assert KEYED["entity"] == {"properties", "attribute_types"}
        assert KEYED["connection"] == {"metadata"}

    def test_a_change_set_reaches_a_connection_and_a_proposal_still_does_not(self) -> None:
        """The proposal's union is unchanged by the change set's: a connection has no GAR."""
        assert IN_A_CHANGE_SET == ("entity", "connection")
        assert "connection" not in PROPOSABLE

    def test_a_create_states_no_field_an_edit_could_also_change(self) -> None:
        for kind in IN_A_CHANGE_SET:
            assert not CREATION[kind] & CONTENT[kind]
            assert creatable(kind) == CONTENT[kind] | CREATION[kind]

    def test_a_connection_address_is_the_catalogues(self) -> None:
        names = {part.name for part in dataclasses.fields(ConnectionAddress)}
        assert names == ADDRESSING["connection"]


class TestMovedSinceIsTheRebasesRule:
    @pytest.mark.parametrize(
        ("base", "current", "proposed", "moved"),
        [
            pytest.param("a", "a", "b", False, id="unmoved"),
            pytest.param("a", "b", "b", False, id="already-agrees"),
            pytest.param("a", "c", "b", True, id="someone-else-changed-it"),
            pytest.param(["x"], ("x",), ["y"], False, id="a-list-and-a-tuple-are-one-value"),
            pytest.param("a", " a\n", "b", False, id="edge-whitespace-is-not-a-move"),
        ],
    )
    def test_the_rule(self, base: object, current: object, proposed: object, moved: bool) -> None:
        assert moved_since(base=base, current=current, proposed=proposed) is moved

    def test_the_rebase_asks_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Neutered, the rebase reports no drift: it has no second copy of the rule to fall back on."""
        edit = ProposalEdit(kind="entity", artifact_id="ENT@1.a", fields={"name": "b"})
        assert fields_moved_upstream(edit, {"name": "a"}, {"name": "c"}) == ("name",)

        monkeypatch.setattr(integration_detection, "moved_since", lambda **_: False)
        assert fields_moved_upstream(edit, {"name": "a"}, {"name": "c"}) == ()

    def test_a_change_set_asks_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.application.change_sets import base as base_module  # noqa: PLC0415

        assert has_moved(BaseValue("a"), current="c", proposed="b")
        monkeypatch.setattr(base_module, "moved_since", lambda **_: False)
        assert not has_moved(BaseValue("a"), current="c", proposed="b")
        assert not has_moved(BaseRevision(prose_revision("a")), current="c", proposed="b")

    def test_prose_moves_by_its_revision(self) -> None:
        base = BaseRevision(prose_revision("the old summary"))
        assert not has_moved(base, current="the old summary\n", proposed="a new one")
        assert not has_moved(base, current="a new one", proposed="a new one")
        assert has_moved(base, current="what someone else wrote", proposed="a new one")

    def test_absent_prose_and_empty_prose_are_one_text(self) -> None:
        assert prose_revision(None) == prose_revision("") == prose_revision("  \n")


def test_a_file_revision_and_a_content_revision_are_one_function(tmp_path: Path) -> None:
    """A diagram's base revision and a prose field's are comparable because they are the same digest."""
    written = tmp_path / "diagram.puml"
    written.write_bytes("@startuml\n@enduml\n".encode())

    assert compute_revision(written) == content_revision(written.read_bytes())
    assert len(content_revision(b"")) == 16


class TestContested:
    def test_names_every_key_claimed_twice_and_who_claimed_it_in_order(self) -> None:
        claims = [("a", 1), ("b", 1), ("c", 2), ("a", 3), ("b", 2), ("a", 2)]
        assert contested(claims) == {"a": (1, 3, 2), "b": (1, 2)}

    def test_the_two_claims_need_not_be_adjacent(self) -> None:
        assert contested([("a", 1), ("b", 2), ("c", 3), ("a", 4)]) == {"a": (1, 4)}

    def test_one_party_claiming_a_key_twice_is_not_a_contest(self) -> None:
        assert contested([("a", 1), ("a", 1)]) == {}

    def test_keys_come_back_in_the_order_they_were_first_contested(self) -> None:
        assert list(contested([("a", 1), ("b", 1), ("b", 2), ("a", 2)])) == ["b", "a"]
