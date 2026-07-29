"""Tests for the domain artifact_id module (WS1 — canonical identity)."""

import pytest

from src.domain.artifact_id import (
    ConnectionKey,
    EntityId,
    MalformedArtifactIdError,
    parse_connection_id,
    parse_entity_id,
    slug_of,
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
