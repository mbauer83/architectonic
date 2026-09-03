"""A symmetric relationship is one connection, whichever endpoint names it.

The ontology says `archimate-association` is symmetric; the index agrees, storing it under *both*
endpoints in a `symmetric` bucket that belongs to neither direction; and creation admits it from
either side. Only the delete path disagreed. It compared raw `(source, type, target)` triples, so:

* naming the connection from the end that did not happen to record it reported it missing, and
* a batch deleting an entity *and* that connection could not recognise its own connection delete,
  because the blocker built the key one way round and the request the other. The author was told the
  connection must also be deleted while deleting it, and the only way through was two passes with the
  endpoints named the way the file happened to store them.

The fix is one key function, bound to one answer about symmetry and passed to both sides — the whole
failure was two places answering the same question differently.

**Directed relationships must not gain the same tolerance**, and that is the risk in fixing this:
`A -> B` and `B -> A` are different connections, so a lookup that matched on endpoint *sets* would
answer a request to delete one with the other and report success. The last two tests are that risk,
pinned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_delete

#: The one symmetric relation type the shipped ontology declares.
SYMMETRIC = "archimate-association"
DIRECTED = "archimate-influence"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type="value", name=name, dry_run=False, repo_root=str(repo)
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _connect(repo: Path, source: str, target: str, conn_type: str) -> None:
    result = mcp.artifact_add_connection(
        source_entity=source, connection_type=conn_type, target_entity=target,
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result


def _delete(repo: Path, *items: dict) -> list[dict]:
    return list(artifact_bulk_delete(items=list(items), dry_run=False, repo_root=str(repo))["results"])


def _recorded(repo: Path) -> list[str]:
    """Every connection heading the repository still holds, as `source-stem: type → target`."""
    return sorted(
        f"{path.name.split('.')[1]}: {line[4:]}"
        for path in repo.rglob("*.outgoing.md")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    )


class TestASymmetricConnectionIsReachableFromBothEnds:
    def test_deleting_it_by_the_endpoint_that_did_not_record_it(self, repo: Path) -> None:
        a, b = _entity(repo, "A"), _entity(repo, "B")
        _connect(repo, a, b, SYMMETRIC)

        results = _delete(repo, {
            "op": "delete_connection", "source_entity": b,
            "connection_type": SYMMETRIC, "target_entity": a,
        })

        assert [r.get("wrote") for r in results] == [True], results
        assert _recorded(repo) == []

    def test_the_entity_and_its_connection_go_in_one_pass(self, repo: Path) -> None:
        """The reported friction: this took two passes, because the batch blocked on its own delete."""
        a, b = _entity(repo, "A"), _entity(repo, "B")
        _connect(repo, a, b, SYMMETRIC)

        results = _delete(
            repo,
            {"op": "delete_connection", "source_entity": b,
             "connection_type": SYMMETRIC, "target_entity": a},
            {"op": "delete_entity", "artifact_id": b},
        )

        assert [r.get("wrote") for r in results] == [True, True], results
        assert _recorded(repo) == []
        assert not list(repo.rglob(f"{b}.md")), "the entity survived a batch that reported deleting it"

    def test_naming_it_the_way_it_was_stored_still_works(self, repo: Path) -> None:
        """The control. Without it the test above could pass by breaking the ordinary case."""
        a, b = _entity(repo, "A"), _entity(repo, "B")
        _connect(repo, a, b, SYMMETRIC)

        results = _delete(
            repo,
            {"op": "delete_connection", "source_entity": a,
             "connection_type": SYMMETRIC, "target_entity": b},
            {"op": "delete_entity", "artifact_id": b},
        )

        assert [r.get("wrote") for r in results] == [True, True], results
        assert _recorded(repo) == []


class TestADirectedConnectionKeepsItsDirection:
    def test_deleting_one_direction_leaves_the_other(self, repo: Path) -> None:
        """The risk in the fix: matching on endpoint *sets* would take the wrong connection."""
        a, b = _entity(repo, "A"), _entity(repo, "B")
        _connect(repo, a, b, DIRECTED)
        _connect(repo, b, a, DIRECTED)

        results = _delete(repo, {
            "op": "delete_connection", "source_entity": a,
            "connection_type": DIRECTED, "target_entity": b,
        })

        assert [r.get("wrote") for r in results] == [True], results
        remaining = _recorded(repo)
        assert len(remaining) == 1, remaining
        assert remaining[0].endswith(a), f"the surviving connection should be B -> A, got {remaining[0]}"

    def test_naming_it_from_the_far_end_is_still_refused(self, repo: Path) -> None:
        a, b = _entity(repo, "A"), _entity(repo, "B")
        _connect(repo, a, b, DIRECTED)

        results = _delete(repo, {
            "op": "delete_connection", "source_entity": b,
            "connection_type": DIRECTED, "target_entity": a,
        })

        assert results[0].get("wrote") is False
        assert results[0].get("error"), "a directed connection that does not exist must say so"
        assert len(_recorded(repo)) == 1
