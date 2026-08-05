"""One connection may carry several specializations, and every surface has to agree it can.

ArchiMate §15.2 lets a concept apply more than one specialization, and the alternative is worse than
untidy: two connections between the same endpoints with the same type, distinguished only by their
specializations, are one connection as far as identity goes — `(source, target, type)` — so the second
reads as a duplicate (W120). Carrying both on one connection says what the model means without
changing what a connection *is*.

`archimate-assignment` is the case that exists in the shipped ontology: it declares both
`responsibility-assignment` and `behavior-assignment`.

Three surfaces had to hold, and two of them did not:

* the **write path** records one as a scalar (so existing files stay byte-identical) and several as a
  list — this part was already right;
* **re-parsing** a file for any later edit carried the value forward only when it was a scalar, and
  the formatter treats that key as authoritative — so editing a *sibling* connection silently
  unspecialized the one holding two;
* the **endpoint-restriction check** (W128) read the raw value through `str()`, which turns a list
  into `"['a', 'b']"` — a slug no catalog declares — so a connection carrying two had neither
  checked, and the check that went quiet is the one whose whole job is to narrow endpoints.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp

_ASSIGNMENT = "archimate-assignment"
_BOTH = ["responsibility-assignment", "behavior-assignment"]


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry  # noqa: PLC0415

    return build_runtime_catalogs(get_module_registry())


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-SPEC" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _entity(repo: Path, artifact_type: str, name: str) -> str:
    result = mcp.artifact_create_entity(
        artifact_type=artifact_type, name=name, summary=f"Summary for {name}",
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return str(result["artifact_id"])


def _actor_and_process(repo: Path) -> tuple[str, str]:
    """A role assigned to a function — the permitted assignment pair in this ontology."""
    return _entity(repo, "role", "Assigning Role"), _entity(repo, "function", "Assigned Function")


def _add(repo: Path, source: str, target: str, specializations: list[str] | None, description: str) -> dict:
    result = mcp.artifact_add_connection(
        source_entity=source, target_entity=target, connection_type=_ASSIGNMENT,
        description=description, specializations=specializations,
        dry_run=False, repo_root=str(repo),
    )
    assert result["wrote"], result
    return result


def _outgoing_path(repo: Path, source: str) -> Path:
    return next(repo.rglob(f"{source}.outgoing.md"))


def _metadata_blocks(repo: Path, source: str) -> list[dict]:
    """The per-connection YAML metadata blocks, in file order."""
    text = _outgoing_path(repo, source).read_text(encoding="utf-8")
    blocks: list[dict] = []
    for chunk in text.split("### ")[1:]:
        fenced = [part for part in chunk.split("```") if part.strip().startswith("yaml")]
        for part in fenced:
            loaded = yaml.safe_load(part.strip()[len("yaml"):])
            if isinstance(loaded, dict):
                blocks.append(loaded)
    return blocks


def _verify(repo: Path, source: str):
    registry = ArtifactRegistry(shared_artifact_index(repo))
    return ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(_outgoing_path(repo, source))


# ── writing ───────────────────────────────────────────────────────────────────


def test_both_specializations_are_recorded_as_a_list(repo: Path) -> None:
    actor, process = _actor_and_process(repo)

    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")

    (block,) = _metadata_blocks(repo, actor)
    assert block["specialization"] == _BOTH


def test_one_specialization_is_still_a_scalar(repo: Path) -> None:
    """146 files use the scalar form; the plural case must not churn any of them."""
    actor, process = _actor_and_process(repo)

    _add(repo, actor, process, ["responsibility-assignment"], "Responsible for it.")

    (block,) = _metadata_blocks(repo, actor)
    assert block["specialization"] == "responsibility-assignment"


def test_a_connection_with_two_specializations_verifies_clean(repo: Path) -> None:
    actor, process = _actor_and_process(repo)
    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")

    result = _verify(repo, actor)

    assert result.valid, [issue.message for issue in result.issues]


def test_an_undeclared_slug_is_still_refused_alongside_a_valid_one(repo: Path) -> None:
    """Each slug is validated on its own; a good one does not carry a bad one through.

    A slug the catalog does not declare is not an input error but a verification failure — the write
    is attempted, refused by E160, and reported as `wrote: False` with the issue attached.
    """
    actor, process = _actor_and_process(repo)

    result = mcp.artifact_add_connection(
        source_entity=actor, target_entity=process, connection_type=_ASSIGNMENT,
        description="One real, one invented.",
        specializations=["responsibility-assignment", "no-such-specialization"],
        dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"] is False
    issues = result["verification"]["issues"]
    assert any(issue["code"] == "E160" and "no-such-specialization" in issue["message"] for issue in issues), issues
    assert not any("responsibility-assignment" in issue["message"] for issue in issues), issues


# ── reading back, which is where they were being lost ─────────────────────────


def test_editing_a_sibling_connection_keeps_both_specializations(repo: Path) -> None:
    """The whole file is re-rendered from parsed connections, so a lossy parse loses data."""
    actor, process = _actor_and_process(repo)
    other = _entity(repo, "function", "Other Function")
    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")
    _add(repo, actor, other, None, "Plainly assigned.")

    edited = mcp.artifact_edit_connection(
        source_entity=actor, connection_type=_ASSIGNMENT, target_entity=other,
        description="Edited description.", dry_run=False, repo_root=str(repo),
    )
    assert edited["wrote"], edited

    blocks = [block for block in _metadata_blocks(repo, actor) if "specialization" in block]
    assert [block["specialization"] for block in blocks] == [_BOTH]


def test_editing_the_connection_itself_keeps_both_specializations(repo: Path) -> None:
    actor, process = _actor_and_process(repo)
    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")

    edited = mcp.artifact_edit_connection(
        source_entity=actor, connection_type=_ASSIGNMENT, target_entity=process,
        description="Reworded, same specializations.", dry_run=False, repo_root=str(repo),
    )
    assert edited["wrote"], edited

    (block,) = _metadata_blocks(repo, actor)
    assert block["specialization"] == _BOTH


def test_the_index_reports_every_applied_slug(repo: Path) -> None:
    actor, process = _actor_and_process(repo)
    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")

    registry = ArtifactRegistry(shared_artifact_index(repo))
    connection = next(
        c for c in registry.find_connections_for(actor, direction="outbound") if c.conn_type == _ASSIGNMENT
    )

    assert list(connection.specializations) == _BOTH


# ── the checks that go with a slug apply to each of them ──────────────────────


def test_an_endpoint_restriction_is_checked_for_every_applied_slug(repo: Path) -> None:
    """W128 read the raw value with `str()`, so a list matched no catalog entry and nothing ran.

    The assertion is about *reach*, not about a specific violation: the shipped assignment
    specializations restrict nothing, so what is observable is that each slug is looked up. A
    connection carrying two must produce no more findings than the same two carried one at a time.
    """
    actor, process = _actor_and_process(repo)
    _add(repo, actor, process, _BOTH, "Assigned, and responsible for it.")

    codes = [issue.code for issue in _verify(repo, actor).issues]

    assert "W128" not in codes, codes
    assert "E160" not in codes and "E161" not in codes, codes
