"""The generated fixture workspace is a repository the product accepts, built by the product.

Three registers are blocked on this one artefact — 57 dark REST writes, 47 MCP write tools, 33 GUI
write methods — so the fixture has to be trustworthy before anything is written against it. Two claims
matter and each is asserted below.

**It is built through the write path, not around it.** Every artifact is authored by
`artifact_create_entity` and friends with `dry_run=False`. A generator that used `Path.write_text`
would produce a workspace that looks right and proves nothing, and would keep working while the write
layer was broken — the exact inversion of what a write fixture is for.

**It verifies clean.** Content the product's own verifier rejects is worse than no fixture: every walk
run against it would report failures belonging to the fixture, and the first few would be debugged as
product defects. Asserted through `ArtifactVerifier.verify_all`, which is what `artifact_verify` runs.

The content checklist itself — populated *and* sparse instances of each kind — is asserted here too,
because that is the whole reason to generate rather than curate: the dogfood repository only ever
showed the read walks the *absent* branch of every optional field, and a fixture that repeated that
would remove none of the frictions it exists to remove.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.quality.fixture_workspace import ENGAGEMENT, FixtureWorkspace, build_fixture_workspace


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> FixtureWorkspace:
    """Built once: generation runs the real write path and is the expensive part of this module."""
    return build_fixture_workspace(tmp_path_factory.mktemp("fixture-workspace"))


def test_both_roots_exist_with_arch_repo_defaults(workspace: FixtureWorkspace) -> None:
    for root in (workspace.engagement_root, workspace.enterprise_root):
        assert (root / "model").is_dir(), root
        assert (root / ".arch-repo" / "config.yaml").is_file(), root
        # The document schemas are what make a document write succeed rather than be refused.
        assert (root / ".arch-repo" / "documents" / "adr.json").is_file(), root
    assert ENGAGEMENT in workspace.engagement_root.parts


def test_every_kind_the_checklist_names_was_authored(workspace: FixtureWorkspace) -> None:
    for kind, least in (("entity", 2), ("connection", 1), ("document", 2), ("diagram", 1)):
        assert len(workspace.ids(kind)) >= least, (kind, workspace.ids(kind))


def test_each_artifact_landed_as_a_file_on_disk(workspace: FixtureWorkspace) -> None:
    """The ids the generator reports must correspond to files, or a walk addresses nothing."""
    stems = {path.stem for path in workspace.engagement_root.rglob("*.md")}
    stems |= {path.stem for path in workspace.engagement_root.rglob("*.puml")}
    for kind in ("entity", "document", "diagram"):
        for identifier in workspace.ids(kind):
            assert identifier in stems, f"{kind} {identifier} has no file"


def test_the_populated_entity_carries_optional_fields_and_the_sparse_one_does_not(
    workspace: FixtureWorkspace,
) -> None:
    """The point of the checklist: both branches of every optional field exist to be read."""
    populated, sparse = workspace.connected_entities
    populated_text = _entity_text(workspace, populated)
    sparse_text = _entity_text(workspace, sparse)

    assert "keywords:" in populated_text
    assert "keywords:" not in sparse_text, (
        "the sparse entity carries keywords, so nothing in the fixture exercises the absent branch"
    )


def test_the_unreferenced_entity_really_is_unreferenced(workspace: FixtureWorkspace) -> None:
    """What a delete preview needs. Asserted because the generator's promise is easy to break: adding
    one convenience connection from it would silently remove the only entity safe to delete."""
    target = workspace.unreferenced_entity
    short = ".".join(target.split(".")[:2])
    for path in workspace.engagement_root.rglob("*.outgoing.md"):
        text = path.read_text(encoding="utf-8")
        assert short not in text, f"{path.name} references the entity meant to be unreferenced"


def test_the_two_connected_entities_are_joined_by_a_real_connection(
    workspace: FixtureWorkspace,
) -> None:
    source, target = workspace.connected_entities
    outgoing = [p for p in workspace.engagement_root.rglob("*.outgoing.md")]
    assert outgoing, "no connection file was written"
    joined = any(
        ".".join(source.split(".")[:2]) in p.read_text(encoding="utf-8")
        and ".".join(target.split(".")[:2]) in p.read_text(encoding="utf-8")
        for p in outgoing
    )
    assert joined, [p.name for p in outgoing]


def test_the_generated_workspace_verifies_clean(workspace: FixtureWorkspace) -> None:
    """Through the product's own verifier, because a fixture the product rejects is worse than none.

    Without this, every walk run against the fixture would report failures that belong to the fixture,
    and the first few would be investigated as product defects.
    """
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.artifact_index import shared_artifact_index

    index = shared_artifact_index(workspace.engagement_root)
    try:
        verifier = ArtifactVerifier(
            ArtifactRegistry(index), catalogs=build_runtime_catalogs(get_module_registry())
        )
        results = verifier.verify_all(workspace.engagement_root, include_diagrams=False)
    finally:
        index.close()

    assert results, "the verifier found nothing to verify, so this assertion proves nothing"
    invalid = [
        f"{r.path.name}: {[i.message for i in r.issues if i.severity == 'error']}"
        for r in results
        if not r.valid
    ]
    assert invalid == [], invalid


def test_a_second_build_into_one_root_is_refused_rather_than_duplicating(tmp_path: Path) -> None:
    """A fixture root is single-use, and the product is what enforces that.

    I expected generation to be additive and wrote this to assert it. It is not: entity type + name is
    unique across repositories, so the second build's first entity is refused by name. That is the
    better behaviour — a fixture root that silently accumulated two of everything would give a write
    walk two candidates where its assertions assume one — so the test records the refusal instead.

    It also happens to be a genuine round trip: the uniqueness rule is enforced by the same write path
    the generator uses, so this is the rule being exercised, not just described.
    """
    build_fixture_workspace(tmp_path)
    with pytest.raises(RuntimeError, match="already exists"):
        build_fixture_workspace(tmp_path)


def _entity_text(workspace: FixtureWorkspace, identifier: str) -> str:
    matches = [p for p in workspace.engagement_root.rglob(f"{identifier}.md")]
    assert matches, f"no file for {identifier}"
    return matches[0].read_text(encoding="utf-8")
