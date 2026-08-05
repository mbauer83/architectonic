"""A connection whose source id ends in a hyphen is addressable like any other.

The random key is drawn from ``letters + digits + "-_"``, so roughly one entity in sixty-four gets a
key ending in ``-`` — and the composite connection id joins two ids with ``---``. Splitting on the
first three hyphens in a row took the key's own hyphen plus two of the separator, leaving a source
one character short and a target with a leading ``-``.

Nothing crashed. The connection simply could not be found from either end, so removing it answered
"connection not found for source entity" for a connection that was right there. In the REST write
walk that surfaced as `admin_delete_connection` failing on about one run in sixty-four, which read as
a flaky test for months. This drives the condition deliberately instead of waiting for the dice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.artifact_id import parse_connection_id, stable_conn_id
from src.infrastructure.mcp import mcp_artifact_server as mcp

#: A key ending in the character that made the separator ambiguous. Slugged, as a minted id is —
#: the composite is built from the *stable* forms, which is why the failing walk showed slugless
#: endpoints joined by four hyphens.
HYPHEN_KEYED = "APP@1785971770.O_xvx-.hyphen-keyed"
TARGET = "APP@1785971770.MWX6h1.the-target"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    for artifact_id, name in ((HYPHEN_KEYED, "Hyphen Keyed"), (TARGET, "The Target")):
        result = mcp.artifact_create_entity(
            artifact_type="application-component", name=name, artifact_id=artifact_id,
            dry_run=False, repo_root=str(root),
        )
        assert result["wrote"], result
    return root


def _connections_in(repo: Path) -> list[str]:
    return [
        line.strip()
        for path in (repo / "model").rglob("*.outgoing.md")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("### archimate-")
    ]


def test_a_connection_from_a_hyphen_keyed_entity_can_be_removed(repo: Path) -> None:
    added = mcp.artifact_add_connection(
        source_entity=HYPHEN_KEYED, connection_type="archimate-serving", target_entity=TARGET,
        dry_run=False, repo_root=str(repo),
    )
    assert added["wrote"], added
    assert _connections_in(repo), "the connection was never written"

    # Addressed the way `DELETE /admin/api/connections/{id}` addresses it: one composite string,
    # parsed back into endpoints. That parse is where the defect lived — removing by two separate
    # endpoint arguments never touches it, which is why the walk was the only thing that ever failed.
    composite = stable_conn_id(f"{HYPHEN_KEYED}---{TARGET}@@archimate-serving")
    key = parse_connection_id(composite)
    assert key.src_short == "APP@1785971770.O_xvx-", f"the composite parsed to {key.src_short!r}"

    removed = mcp.artifact_edit_connection(
        source_entity=key.src_short, connection_type=key.type, target_entity=key.tgt_short,
        operation="remove", dry_run=False, repo_root=str(repo),
    )

    assert removed["wrote"], removed
    assert _connections_in(repo) == [], "the removal reported success without happening"
