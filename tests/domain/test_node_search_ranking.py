"""One search rule, expressed twice by necessity, held to one answer.

`search_nodes` was implemented four times: an identical in-memory substring filter in three stores, and
SQL in the SQLCipher one. The SQL had a ranking the other three did not — `ORDER BY CASE WHEN name LIKE ?
THEN 0 ELSE 1 END` — so a node matched by *name* came first there and nowhere else. Four backends, two
different answers to one question, and nothing failed: the answer was just quietly worse depending on
which store was configured.

The rule now lives in `src/domain/assurance/node_search.py` and the three in-memory stores call it. The
SQL stays SQL, because a store that can filter and rank in the database must — otherwise `search_nodes`
becomes "load every node first". So the rule has two expressions on purpose, which is precisely the
arrangement that drifts, and this file is what stops it: the SQL's ordering clause is asserted to encode
the same ranking the domain function computes.

Fixtures are this file's own, so the assertions are exact — which they could not be against a real store.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domain.assurance.node_search import (
    SEARCHED_FIELDS,
    matches_node,
    rank_node_matches,
)

_NODES = [
    {"node_id": "1", "name": "Brake failure", "content_text": "unrelated"},
    {"node_id": "2", "name": "Unrelated", "content_text": "mentions brake in the body"},
    {"node_id": "3", "name": "Brake sensor", "content_text": "also mentions brake"},
    {"node_id": "4", "name": "Nothing", "content_text": "nothing here"},
]


class TestWhatMatches:
    def test_a_name_or_a_body_match_both_count(self) -> None:
        assert matches_node(_NODES[0], "brake") is True
        assert matches_node(_NODES[1], "brake") is True
        assert matches_node(_NODES[3], "brake") is False

    def test_matching_ignores_case_in_both_directions(self) -> None:
        assert matches_node({"name": "BRAKE"}, "brake") is True
        assert matches_node({"name": "brake"}, "BRAKE") is True

    def test_a_missing_field_is_not_an_error(self) -> None:
        """Stores answer partial records; a node with no `content_text` must not raise."""
        assert matches_node({"name": "Brake"}, "brake") is True
        assert matches_node({"content_text": "brake"}, "brake") is True
        assert matches_node({}, "brake") is False


class TestHowItRanks:
    def test_a_name_match_outranks_a_body_match(self) -> None:
        """The behaviour three of four backends silently lacked."""
        ordered = [node["node_id"] for node in rank_node_matches(_NODES, "brake")]

        assert ordered == ["1", "3", "2"], ordered

    def test_within_one_rank_the_stores_own_order_is_kept(self) -> None:
        """A ranking *above* the store's ordering, not instead of it — the SQL's `, created_at` tail.

        Reversing the input must reverse the two name matches relative to each other while leaving the
        body match last, which distinguishes a stable sort from one that happens to agree.
        """
        ordered = [node["node_id"] for node in rank_node_matches(list(reversed(_NODES)), "brake")]

        assert ordered == ["3", "1", "2"], ordered

    def test_the_limit_is_applied_after_ranking_not_before(self) -> None:
        """Otherwise a limit of one returns whichever matched first in list order, which is the bug the
        in-memory version had: it broke out of the loop at `limit` and never ranked at all."""
        ordered = [node["node_id"] for node in rank_node_matches(list(reversed(_NODES)), "brake", limit=1)]

        assert ordered == ["3"], ordered

    def test_an_empty_query_matches_everything(self) -> None:
        assert len(rank_node_matches(_NODES, "")) == len(_NODES)

    def test_the_answer_is_a_copy_rather_than_the_caller_s_own_dicts(self) -> None:
        """A store handing back its internal mappings lets a caller mutate the store by accident."""
        result = rank_node_matches(_NODES, "brake")
        result[0]["name"] = "mutated"

        assert _NODES[0]["name"] == "Brake failure"


class TestTheSqlExpressesTheSameRule:
    """The half a shared function cannot enforce: the SQLCipher store's own SQL.

    Read out of the source rather than executed, because running it needs a SQLCipher store and this is a
    statement about the *query*, not about a database. Crude, and the right crudeness: what must not
    happen is the ranking clause quietly disappearing, and a source assertion catches exactly that.
    """

    @pytest.fixture()
    def sql(self) -> str:
        source = Path("src/infrastructure/assurance/_sqlcipher_store.py").read_text(encoding="utf-8")
        match = re.search(r"def search_nodes\(.*?(?=\n    def )", source, re.S)
        assert match is not None, "the SQLCipher store no longer has a search_nodes"
        return match.group(0)

    def test_it_matches_on_the_same_fields(self, sql: str) -> None:
        for field in SEARCHED_FIELDS:
            assert f"{field} LIKE ?" in sql, (field, sql)

    def test_it_ranks_a_name_match_first(self, sql: str) -> None:
        collapsed = " ".join(sql.split())
        assert "CASE WHEN name LIKE ? THEN 0 ELSE 1 END" in collapsed, collapsed

    def test_it_keeps_the_stores_own_order_within_a_rank(self, sql: str) -> None:
        """`, created_at` after the rank — the SQL's version of the stable sort asserted above."""
        collapsed = " ".join(sql.split())
        assert "ELSE 1 END, created_at" in collapsed, collapsed


def test_every_in_memory_store_uses_the_shared_rule() -> None:
    """The other half: no store may quietly grow its own filter back.

    Named as source inspection because that is what it is. Three stores had the same body once; a fourth
    copy arriving is the failure this catches, and it would arrive as a *local* loop rather than as a
    call.
    """
    for name in ("_private_git_store", "_encrypted_private_git_store", "_pocketbase_store"):
        source = Path(f"src/infrastructure/assurance/{name}.py").read_text(encoding="utf-8")
        assert "rank_node_matches(" in source, name
        assert "content_text\", \"\")).lower()" not in source, (
            f"{name} has grown its own matching rule back"
        )
