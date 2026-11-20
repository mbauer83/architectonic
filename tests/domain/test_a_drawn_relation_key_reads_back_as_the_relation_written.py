"""The key written for a drawn relation reads back as that relation, and a rule key as that rule.

Two small syntaxes a layout and an edge label are keyed by. Each has one writer and one reader, held
here as a pair over what the form permits: any connection between any two entities, drawn between
base instances or occurrences, spelled with slugs or without.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.domain.diagrams.authored_groupings import (
    GroupingRule,
    MalformedGroupings,
    RuleKey,
    is_rule_key,
    read_rule_key,
)
from src.domain.diagrams.relation_key import (
    DrawnRelationKey,
    MalformedRelationKey,
    alias_pair_of,
    drawn_relation_key,
    read_relation_key,
)

_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_slugs = st.none() | st.from_regex(r"[a-z][a-z0-9-]{0,20}[a-z0-9]", fullmatch=True)
_entities = st.builds(
    lambda prefix, epoch, random, slug: (f"{prefix}@{epoch}.{random}", slug),
    st.sampled_from(["APP", "BOB", "PRC", "JCT"]),
    st.integers(1_000_000_000, 1_999_999_999),
    st.text(_LETTERS, min_size=6, max_size=7),
    _slugs,
)
_occurrences = st.none() | st.text(_LETTERS + "-_.", min_size=1, max_size=14).map(lambda text: f"occ-{text}")


def _spelled(entity: tuple[str, str | None]) -> str:
    stem, slug = entity
    return f"{stem}.{slug}" if slug else stem


@given(_entities, _entities, st.sampled_from(["archimate-serving", "archimate-flow"]), _occurrences, _occurrences)
def test_a_key_reads_back_as_the_relation_it_was_written_for(
    source: tuple[str, str | None], target: tuple[str, str | None], conn_type: str,
    source_occurrence: str | None, target_occurrence: str | None,
) -> None:
    connection = f"{_spelled(source)}---{_spelled(target)}@@{conn_type}"

    written = drawn_relation_key(
        connection, source=_spelled(source), target=_spelled(target),
        source_instance=source_occurrence or _spelled(source),
        target_instance=target_occurrence or _spelled(target),
    )
    read = read_relation_key(written.text)

    assert read == written
    assert read.connection == f"{source[0]}---{target[0]}@@{conn_type}", "the connection is held slug-free"
    if source_occurrence is None and target_occurrence is None:
        assert read.ends is None and read.text == read.connection
    else:
        assert read.ends == (source_occurrence or source[0], target_occurrence or target[0])


def test_two_relations_between_one_pair_have_two_keys() -> None:
    """What the alias pair could not say, and the reason the key changed."""
    serving = drawn_relation_key(
        "APP@1.aaaaaa---APP@2.bbbbbb@@archimate-serving", source="APP@1.aaaaaa", target="APP@2.bbbbbb",
        source_instance="APP@1.aaaaaa", target_instance="APP@2.bbbbbb",
    )
    flow = drawn_relation_key(
        "APP@1.aaaaaa---APP@2.bbbbbb@@archimate-flow", source="APP@1.aaaaaa", target="APP@2.bbbbbb",
        source_instance="APP@1.aaaaaa", target_instance="APP@2.bbbbbb",
    )

    assert serving.text != flow.text


def test_a_connection_a_diagram_holds_is_keyed_by_its_own_id() -> None:
    assert read_relation_key("svc:c4-uses:db") == DrawnRelationKey("svc:c4-uses:db")
    assert read_relation_key("svc::db") == DrawnRelationKey("svc::db")


@pytest.mark.parametrize("retired", ["APP_a:APP_b", "C_svc_0:SS_sys_0", "APP_hkrdtm:APP_Z_fI_N"])
def test_the_retired_alias_pair_is_recognised_and_refused_with_what_to_run(retired: str) -> None:
    assert alias_pair_of(retired) is not None
    with pytest.raises(MalformedRelationKey, match="arch-repair upgrade"):
        read_relation_key(retired)


@pytest.mark.parametrize("key", ["", "  ", "A@1.aaaaaa---B@2.bbbbbb@@serving@>B@2.bbbbbb", "no-connection>x"])
def test_what_is_not_a_key_is_refused(key: str) -> None:
    with pytest.raises(MalformedRelationKey):
        read_relation_key(key)


_names = st.from_regex(r"[a-z0-9][a-z0-9_-]{0,16}", fullmatch=True)
_rules = st.builds(GroupingRule, st.sampled_from(["domain", "type"]), _names)


@given(st.lists(_rules, min_size=1, max_size=4).map(tuple), st.one_of(st.just(1), st.integers(2, 40)))
def test_a_rule_key_reads_back_as_the_rule_path_written(path: tuple[GroupingRule, ...], ordinal: int) -> None:
    written = RuleKey(path, ordinal)

    assert is_rule_key(written.text)
    assert read_rule_key(written.text) == written


@pytest.mark.parametrize(
    "text", ["rule:", "rule:colour=red", "rule:domain=", "rule:domain=Business", "rule:domain=a#1", "rule:domain=a#x",
             "domain=business", "rule:domain=a//type=b"],
)
def test_what_is_not_a_rule_key_is_refused(text: str) -> None:
    with pytest.raises(MalformedGroupings):
        read_rule_key(text)
