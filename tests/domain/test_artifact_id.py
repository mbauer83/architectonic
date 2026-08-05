"""Tests for the domain artifact_id module (WS1 — canonical identity)."""

import pytest

from src.domain.artifact_id import (
    ConnectionKey,
    EntityId,
    MalformedArtifactIdError,
    connection_id_as_written,
    parse_connection_id,
    parse_entity_id,
    slug_of,
    stable_conn_id,
    stable_id,
)


class TestStableId:
    def test_short_form_returned_unchanged(self):
        s = "REQ@1776423712.KG27vK"
        assert stable_id(s) == s

    def test_full_form_strips_slug(self):
        assert stable_id("REQ@1776423712.KG27vK.write-code") == "REQ@1776423712.KG27vK"

    def test_long_slug_stripped_correctly(self):
        long_id = "REQ@1776423712.KG27vK.write-code-using-expressive-typing-where-available"
        assert stable_id(long_id) == "REQ@1776423712.KG27vK"

    def test_slug_drift_yields_same_stable_id(self):
        """Old and new slug forms of the same entity must produce the same stable key."""
        short1 = stable_id("ENT@1776423712.ABC123.cps")
        short2 = stable_id("ENT@1776423712.ABC123.cam-projects-cps")
        assert short1 == short2 == "ENT@1776423712.ABC123"

    def test_never_returns_full_id_for_long_form(self):
        full = "REQ@1776423712.KG27vK.some-slug"
        result = stable_id(full)
        assert result != full
        assert "." in result
        assert result.count(".") == 1


class TestSlugOf:
    def test_short_form_returns_none(self):
        assert slug_of("REQ@1776423712.KG27vK") is None

    def test_full_form_returns_slug(self):
        assert slug_of("REQ@1776423712.KG27vK.write-code") == "write-code"

    def test_long_slug(self):
        assert slug_of("STD@1777137196.ItT-3l.general-coding-guidelines") == "general-coding-guidelines"


class TestParseEntityId:
    def test_short_form_parse(self):
        eid = parse_entity_id("REQ@1776423712.KG27vK")
        assert eid.prefix == "REQ"
        assert eid.epoch == "1776423712"
        assert eid.random == "KG27vK"
        assert eid.slug is None

    def test_full_form_parse(self):
        eid = parse_entity_id("REQ@1776423712.KG27vK.write-code")
        assert eid.prefix == "REQ"
        assert eid.epoch == "1776423712"
        assert eid.random == "KG27vK"
        assert eid.slug == "write-code"

    def test_short_property(self):
        eid = parse_entity_id("REQ@1776423712.KG27vK.some-slug")
        assert eid.short == "REQ@1776423712.KG27vK"

    def test_long_method(self):
        eid = parse_entity_id("REQ@1776423712.KG27vK")
        assert eid.long("new-slug") == "REQ@1776423712.KG27vK.new-slug"

    def test_long_method_replaces_existing_slug(self):
        eid = parse_entity_id("REQ@1776423712.KG27vK.old-slug")
        assert eid.long("new-slug") == "REQ@1776423712.KG27vK.new-slug"

    def test_roundtrip_short_form(self):
        s = "REQ@1776423712.KG27vK"
        eid = parse_entity_id(s)
        assert eid.short == s
        assert stable_id(s) == eid.short

    def test_roundtrip_full_form(self):
        s = "REQ@1776423712.KG27vK.my-slug"
        eid = parse_entity_id(s)
        assert eid.short == stable_id(s)
        assert eid.long(eid.slug) == s  # type: ignore[arg-type]

    def test_slug_drift_same_entity_id(self):
        """Renaming only the slug must not change entity identity."""
        old = parse_entity_id("ENT@1776423712.ABC123.cps")
        new = parse_entity_id("ENT@1776423712.ABC123.cam-projects-cps")
        assert old.short == new.short
        assert old.prefix == new.prefix
        assert old.epoch == new.epoch
        assert old.random == new.random

    def test_random_with_hyphen(self):
        eid = parse_entity_id("STD@1777137196.ItT-3l.general-coding-guidelines")
        assert eid.random == "ItT-3l"
        assert eid.slug == "general-coding-guidelines"

    def test_prefix_minimum_length_2(self):
        eid = parse_entity_id("AB@1000000000.XXXX")
        assert eid.prefix == "AB"

    def test_prefix_maximum_length_6(self):
        eid = parse_entity_id("ARCHIT@1000000000.XXXX")
        assert eid.prefix == "ARCHIT"

    def test_malformed_missing_at(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("REQ1776423712.KG27vK")

    def test_malformed_prefix_too_short(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("R@1776423712.KG27vK")

    def test_malformed_prefix_too_long(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("TOOLONG@1776423712.KG27vK")

    def test_malformed_lowercase_prefix(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("req@1776423712.KG27vK")

    def test_malformed_no_epoch(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("REQ@.KG27vK")

    def test_malformed_empty_string(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("")

    def test_malformed_no_dot(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_entity_id("REQ@1776423712KG27vK")


class TestConnectionKey:
    def test_directed_order_preserved(self):
        key = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@uses")
        assert key.src_short == "REQ@1000.AAA"
        assert key.tgt_short == "ENT@2000.BBB"
        assert key.type == "uses"

    def test_directed_normalized_keeps_order(self):
        key = parse_connection_id("ZZZ@1000.ZZZ---AAA@1000.AAA@@uses")
        normalized = key.normalized(symmetric=False)
        assert normalized.src_short == "ZZZ@1000.ZZZ"
        assert normalized.tgt_short == "AAA@1000.AAA"

    def test_symmetric_normalized_consistent_both_directions(self):
        key_ab = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@associated-with")
        key_ba = parse_connection_id("ENT@2000.BBB---REQ@1000.AAA@@associated-with")
        assert key_ab.normalized(symmetric=True) == key_ba.normalized(symmetric=True)

    def test_equality_across_slug_forms(self):
        """Stale-slug and current-slug connection IDs must compare equal."""
        key1 = parse_connection_id("REQ@1000.AAA.old-slug---ENT@2000.BBB.cps@@uses")
        key2 = parse_connection_id("REQ@1000.AAA.new-slug---ENT@2000.BBB.cam-cps@@uses")
        assert key1 == key2

    def test_equality_short_vs_long_form(self):
        key_short = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@uses")
        key_long = parse_connection_id("REQ@1000.AAA.some-slug---ENT@2000.BBB.other-slug@@uses")
        assert key_short == key_long

    def test_different_endpoints_not_equal(self):
        key1 = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@uses")
        key2 = parse_connection_id("REQ@1000.AAA---ENT@3000.CCC@@uses")
        assert key1 != key2

    def test_different_types_not_equal(self):
        key1 = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@uses")
        key2 = parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@realizes")
        assert key1 != key2

    def test_malformed_missing_double_at(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_connection_id("REQ@1000.AAA---ENT@2000.BBBuses")

    def test_malformed_missing_triple_dash(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_connection_id("REQ@1000.AAAENT@2000.BBB@@uses")

    def test_malformed_empty_type(self):
        with pytest.raises(MalformedArtifactIdError):
            parse_connection_id("REQ@1000.AAA---ENT@2000.BBB@@")

    def test_connection_key_is_frozen(self):
        key = ConnectionKey(src_short="A@1.B", type="uses", tgt_short="C@1.D")
        with pytest.raises((AttributeError, TypeError)):
            key.src_short = "X@1.Y"  # type: ignore[misc]


class TestEntityIdEquality:
    def test_frozen_dataclass_equality(self):
        a = EntityId(prefix="REQ", epoch="1000", random="AAA", slug=None)
        b = EntityId(prefix="REQ", epoch="1000", random="AAA", slug=None)
        assert a == b

    def test_slug_difference_does_not_affect_equality_via_short(self):
        a = parse_entity_id("REQ@1000.AAA.old-slug")
        b = parse_entity_id("REQ@1000.AAA.new-slug")
        assert a != b  # EntityId itself differs on slug
        assert a.short == b.short  # but .short is the same


class TestARandomKeyEndingInAHyphen:
    """The generator draws the random key from ``letters + digits + "-_"``, so about one id in
    sixty-four ends in a hyphen — and the composite connection id joins two ids with ``---``.

    Splitting on the *first* three hyphens in a row therefore took the key's own hyphen plus two of
    the separator: the source came back a character short and the target with a leading ``-``, so the
    connection could not be found from either end. `admin_delete_connection` in the REST write walk
    answered "connection not found for source entity" for a connection that was right there, on
    roughly one run in sixty-four — which is what made it look like a flaky test for months rather
    than a defect. It was found by a run that finally failed and printed the id.
    """

    #: The composite from the failing run, with the source key `O_xvx-`.
    COMPOSITE = "APP@1785971770.O_xvx----APP@1785971770.MWX6h1@@archimate-serving"

    def test_the_source_keeps_its_trailing_hyphen(self) -> None:
        source, _target, _type = connection_id_as_written(self.COMPOSITE)

        assert source == "APP@1785971770.O_xvx-"

    def test_the_target_does_not_gain_a_leading_hyphen(self) -> None:
        _source, target, _type = connection_id_as_written(self.COMPOSITE)

        assert target == "APP@1785971770.MWX6h1"

    def test_the_stable_form_round_trips(self) -> None:
        """`stable_conn_id` is the key every store files a connection under; a truncated source
        endpoint makes the record unfindable from the entity that owns it."""
        assert stable_conn_id(self.COMPOSITE) == (
            "APP@1785971770.O_xvx----APP@1785971770.MWX6h1@@archimate-serving"
        )

    def test_a_hyphen_inside_the_key_is_still_not_a_separator(self) -> None:
        source, target, _type = connection_id_as_written("APP@1.a-b-c---APP@2.cd@@archimate-serving")

        assert (source, target) == ("APP@1.a-b-c", "APP@2.cd")

    def test_a_slug_carrying_hyphens_still_splits_at_the_join(self) -> None:
        source, target, _type = connection_id_as_written(
            "REQ@1.Ab.some-slug---GOL@2.Cd.other-slug@@archimate-realization"
        )

        assert (source, target) == ("REQ@1.Ab.some-slug", "GOL@2.Cd.other-slug")

    def test_something_with_no_separator_at_all_is_still_refused(self) -> None:
        with pytest.raises(MalformedArtifactIdError):
            connection_id_as_written("APP@1.ab@@archimate-serving")
