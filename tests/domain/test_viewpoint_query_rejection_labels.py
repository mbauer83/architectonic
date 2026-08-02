"""A rejection names the mapping it is about exactly once, from either caller.

``query_from_mapping`` is reached two ways — the request-shaped callers (`POST /api/viewpoints/execute`,
the MCP viewpoint tool) hand it the query mapping directly and label it ``"query"``, and
``viewpoint_from_mapping`` hands it a stored definition's ``query:`` block labelled with the slug.
One raise appended the literal ``query:`` itself, so exactly one of the two readings was right per
message: the request caller saw ``query: query: unknown key(s)``, and the definition caller saw
``my-viewpoint: query_schema is required`` with no indication which of a definition's several
mappings had gone wrong.

The convention this holds is the one the rest of the module already follows: the caller supplies the
path, and a parser appends only the key it descends into.
"""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping


def test_a_request_shaped_rejection_names_the_query_once() -> None:
    with pytest.raises(ValueError) as raised:
        query_from_mapping({"concept_scope": ["capability"], "max_hops": 1}, label="query")
    message = str(raised.value)
    assert message.startswith("query: unknown key(s)")
    assert "query: query:" not in message


def test_a_definition_rejection_names_the_definition_and_the_block() -> None:
    with pytest.raises(ValueError) as raised:
        viewpoint_definition_from_mapping(
            {"slug": "my-viewpoint", "query": {"concept_scope": ["capability"]}}
        )
    assert str(raised.value).startswith("viewpoint 'my-viewpoint': query: unknown key(s)")


def test_every_message_from_the_query_parser_carries_the_path_once() -> None:
    # Not only the unknown-key raise: the same label reaches four other messages, and the literal
    # was in exactly one of them, which is how the inconsistency survived.
    for raw, expected in (
        ({"entity_criteria": {}}, "vp: query: query_schema is required"),
        ({"query_schema": 99}, "vp: query: unsupported query_schema 99"),
        ({"query_schema": 1, "include_connected": "nope"}, "vp: query: include_connected must be a list"),
        ({"query_schema": 1, "repo_scope": "nowhere"}, "vp: query: repo_scope 'nowhere' is not one of"),
    ):
        with pytest.raises(ValueError) as raised:
            query_from_mapping(raw, label="vp: query")
        assert str(raised.value).startswith(expected), str(raised.value)
