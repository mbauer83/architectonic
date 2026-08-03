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


class TestTheConfidentialStore:
    """The store is built by the product's CLI, inside the workspace, without touching the developer's.

    Four key-loss incidents are on record, the last of which destroyed the live store on 2026-07-31 by
    copying an unscoped secret onto a scoped account. So the assertions here are about *where* things
    landed as much as about whether they work: a fixture store that works while writing its key to the
    developer's vault would pass every walk and be the fifth incident.
    """

    def test_the_store_and_its_key_are_inside_the_workspace(self, workspace: FixtureWorkspace) -> None:
        from tools.quality.fixture_workspace import assurance_db_path

        store = assurance_db_path(workspace.root)
        assert store.is_file(), store

        # The key, in the fixture's own Fernet vault. Non-empty is the load-bearing half: an empty
        # directory here means `_get_backend` chose something else and the key went somewhere this test
        # cannot see, which is precisely the failure it exists to catch.
        vault = list((workspace.root / "credentials").iterdir())
        assert vault, "the credential directory is empty, so the key was written outside the fixture"

    def test_its_settings_document_is_its_own_and_says_persistent(
        self, workspace: FixtureWorkspace
    ) -> None:
        """The precondition every assurance walk step depends on, asserted at its source.

        `activation_policy` is read from the settings document and from nowhere else, and its default is
        `manual` — under which a newly started process opens nothing and every assurance route answers
        423. CI sets this by mutating the repository's committed `config/settings.yaml`; a fixture must
        not, so it ships its own document and points `ARCH_SETTINGS_PATH` at it.
        """
        import yaml

        from tools.quality.fixture_workspace import assurance_settings_document

        document = assurance_settings_document(workspace.root)
        assert document.is_relative_to(workspace.root), document

        settings = yaml.safe_load(document.read_text(encoding="utf-8"))
        assert settings["storage"]["assurance"]["activation_policy"] == "persistent", settings
        assert settings["storage"]["assurance"]["store_backend"] == "sqlcipher", settings

    def test_it_declares_a_port_nothing_serves(self, workspace: FixtureWorkspace) -> None:
        """Why the settings document carries a port at all, kept as a named claim.

        `arch-assurance unlock` ends with a best-effort POST of `{"authorize": true}` to
        `http://localhost:{backend_port()}/api/assurance/reload`, and `backend_port()` falls back to
        8000 — the developer's backend. Building a fixture store would then authorize a foreign process
        as a side effect. Anything but 8000 would do; port 1 is privileged, so "connection refused" is
        guaranteed rather than merely likely.
        """
        import yaml

        from tools.quality.fixture_workspace import assurance_settings_document

        settings = yaml.safe_load(
            assurance_settings_document(workspace.root).read_text(encoding="utf-8")
        )
        assert settings["backend"]["port"] != 8000, settings

    def test_the_child_environment_removes_the_suites_forbid_flag(
        self, workspace: FixtureWorkspace
    ) -> None:
        """The seam that lets any of this run under pytest, and the reason it is a child at all.

        `tests/conftest.py` sets `ARCH_ASSURANCE_FORBID_REAL_CREDENTIAL_BACKEND` for the whole session
        and documents it as never unset, because it has already been bypassed three times by writers it
        could not see. `_get_backend` checks it before the master-password branch and *raises* — so
        `init_store` called in this process fails, and clearing the flag process-wide would be the
        fourth bypass. Removing it for a child that already has a redirected vault is neither.
        """
        import os

        from src.infrastructure.assurance._credential_store import _FORBID_REAL_BACKEND_ENV
        from tools.quality.fixture_workspace import assurance_child_env

        assert os.environ.get(_FORBID_REAL_BACKEND_ENV), (
            "the suite-wide forbid flag is unset, so this test proves nothing about removing it"
        )

        env = assurance_child_env(workspace.root)
        assert _FORBID_REAL_BACKEND_ENV not in env, sorted(env)
        assert env["ARCH_ASSURANCE_MASTER_PASSWORD"], env
        assert Path(env["ARCH_ASSURANCE_CREDENTIALS_DIR"]).is_relative_to(workspace.root)

    def test_every_role_the_read_surface_needs_is_authored(self, workspace: FixtureWorkspace) -> None:
        """The checklist, as roles rather than as a count.

        21 of the 38 dark assurance operations are reads, and a read walk against an empty store proves
        only that an empty store serves empty answers. Each name here is a precondition some read has:
        the filed analysis for a group read, the bare node for the absent branch of every optional
        field, the snapshot and the vulnerability for the eight security reads, the failure mode for the
        matrix. A role that stops being authored fails here rather than as an empty list eight steps
        into a walk.
        """
        roles = workspace.assurance
        for name in (
            "group", "filed_analysis", "analysis", "hazard_node", "bare_node", "failure_mode",
            "edge", "edge_conn_type", "security_anchor", "vulnerability", "security_snapshot",
        ):
            assert getattr(roles, name), name

    def test_the_filed_and_unfiled_analyses_are_different_analyses(
        self, workspace: FixtureWorkspace
    ) -> None:
        """Filing and content are separate gestures in the store, so both states must exist.

        One analysis serving as both would make "what is filed nowhere" and "what is in this group"
        answerable by the same row, which is exactly the conflation the store's shape avoids.
        """
        assert workspace.assurance.filed_analysis != workspace.assurance.analysis

    def test_the_edge_type_came_from_the_ontology(self, workspace: FixtureWorkspace) -> None:
        """The fixture states no vocabulary of its own, and this is where that would break first.

        `add_edge` refuses a pair the ontology does not permit, so a hard-coded connection type would
        make the fixture fail on an ontology change with an illegal-pair refusal nobody expects. The
        authored type is therefore whatever `legal_connection_types` answered for hazard→loss, and
        asserting it is *a* legal type for that pair keeps the fixture honest without naming one.
        """
        from src.infrastructure.assurance.edge_legality import legal_connection_types

        assert workspace.assurance.edge_conn_type in legal_connection_types("hazard", "loss")

    def test_a_missing_role_says_what_to_look_at(self, workspace: FixtureWorkspace) -> None:
        """The failure mode of this whole arrangement is an empty list read as an answer.

        A walk step that asked for a role the content author never wrote would otherwise get an
        `IndexError` naming nothing. The message names the module that authors it.
        """
        from tools.quality.fixture_workspace import _AssuranceRoles

        with pytest.raises(LookupError, match="fixture_assurance_content"):
            _AssuranceRoles({})._one("assurance_group")

    def test_every_assurance_seam_has_one_definition(self, workspace: FixtureWorkspace) -> None:
        """The builder's environment and the served backend's are the same environment.

        Not a style point. The activation gate the builder writes is found again only if the server
        names the same credential *directory*, and a second spelling of it fails closed and silently:
        the store would simply report itself locked, with nothing anywhere saying why. So the backend's
        `_child_env` composes this function rather than restating its four variables.
        """
        from tools.quality.fixture_backend import _child_env
        from tools.quality.fixture_workspace import assurance_child_env

        shared = assurance_child_env(workspace.root)
        served = _child_env(workspace)

        for key in (
            "ARCH_SETTINGS_PATH",
            "ARCH_ASSURANCE_DB_PATH",
            "ARCH_ASSURANCE_CREDENTIALS_DIR",
            "ARCH_ASSURANCE_MASTER_PASSWORD",
            "ARCH_BACKEND_STATE_DIR",
        ):
            assert served[key] == shared[key], key


def _entity_text(workspace: FixtureWorkspace, identifier: str) -> str:
    matches = [p for p in workspace.engagement_root.rglob(f"{identifier}.md")]
    assert matches, f"no file for {identifier}"
    return matches[0].read_text(encoding="utf-8")
