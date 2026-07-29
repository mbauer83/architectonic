"""End-to-end upgrade of a realistic earlier-release deployment through the public CLI.

These tests drive the real upgrade registries (no fixture steps) against the shared
previous-release fixture and prove the safety contract a safe unattended upgrade rests on:

* a dry run writes nothing anywhere and reports every outdated target as pending;
* a first commit migrates every outdated target, a second commit is a no-op;
* a blocker in any discovered target prevents all writes;
* an injected failure after one target has committed yields an accurate partial report
  and a safe resuming rerun;
* a locked encrypted store is blocking, never reported "current";
* an absent store is no target and is never created or claimed migrated;
* content the migrator has no opinion about survives byte-for-byte.

``--deployment-root`` binds the guidance-cache / signals / store paths beneath the fixture
tree, so a test never touches a real global cache or store.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from src.application.deployment_upgrade.steps import signals_snapshot_schema as signals_step
from src.application.repository_upgrade.registry import FORMAT_CONTRACT_VERSION
from src.domain.assurance.signals_schema import SIGNALS_SCHEMA_VERSION
from src.domain.guidance.guidance import GUIDANCE_FORMAT
from src.infrastructure.cli import arch_repair_upgrade as cli
from src.infrastructure.repository_upgrade.config_store import read_format_contract_version
from tests.support.previous_release_deployment import (
    GUIDANCE_BODY,
    UNRELATED_NOTE_BODY,
    build_previous_release_deployment,
    signals_schema_version,
)


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "probe_backend_url", lambda *_a, **_k: False)


#: A guidance cache as the superseded format left it: level-keyed sibling maps, with no tie between
#: an entity type and the domain it belongs to.
SUPERSEDED_GUIDANCE_BODY = """workspace:
  a-topic:
    context: "One workspace stance."
meta_ontologies:
  archimate-4:
    meta_ontology:
      archimate-4:
        context: "Module-wide framing."
    domain:
      motivation:
        context: "Domain framing."
    entity_types:
      goal: {create_when: cw}
"""


def _deployment_args(root: Path, *extra: str) -> list[str]:
    return ["--deployment-root", str(root), *extra]


class TestDryRunPurity:
    def test_dry_run_reports_pending_targets_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy")
        code = cli.main_upgrade(_deployment_args(dep.root, "--json"))
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        kinds = {t["kind"]: t for t in payload["operational_targets"]}
        assert kinds["guidance_cache"]["state"] == "pending"
        assert kinds["signals_sqlite"]["state"] == "pending"
        # Nothing on disk changed:
        assert dep.guidance_doc.read_text(encoding="utf-8") == f"guidance_format: 1\n{GUIDANCE_BODY}"
        assert signals_schema_version(dep.signals_db) is None


class TestFirstAndSecondCommit:
    def test_first_commit_migrates_every_outdated_target(self, tmp_path: Path) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy")
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == 0
        assert dep.guidance_doc.read_text(encoding="utf-8") == f"guidance_format: {GUIDANCE_FORMAT}\n{GUIDANCE_BODY}"
        assert signals_schema_version(dep.signals_db) == SIGNALS_SCHEMA_VERSION
        # Unrelated content survived:
        assert dep.unrelated_note.read_text(encoding="utf-8") == UNRELATED_NOTE_BODY

    def test_second_commit_is_a_no_op(self, tmp_path: Path) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy")
        args = _deployment_args(dep.root, "--commit")
        assert cli.main_upgrade(args) == 0
        after_first = dep.guidance_doc.read_text(encoding="utf-8")
        assert cli.main_upgrade(args) == 0
        assert dep.guidance_doc.read_text(encoding="utf-8") == after_first

    def test_guidance_content_is_re_nested_under_the_domain_the_module_declares(self, tmp_path: Path) -> None:
        """The restructure needs each meta-ontology's declared hierarchy, which only the CLI can
        resolve — so this drives the real command rather than the step, and would catch the wiring
        being dropped even while the step's own tests still pass."""
        dep = build_previous_release_deployment(tmp_path / "deploy", guidance_body=SUPERSEDED_GUIDANCE_BODY)
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == 0
        migrated = yaml.safe_load(dep.guidance_doc.read_text(encoding="utf-8"))
        assert migrated["guidance_format"] == GUIDANCE_FORMAT
        tree = migrated["meta_ontologies"]["archimate-4"]
        assert tree["motivation"]["entity_types"]["goal"] == {"create_when": "cw"}
        assert tree["motivation"]["context"] == "Domain framing."
        assert tree["context"] == "Module-wide framing."
        assert migrated["workspace"] == "One workspace stance."


class TestBlockingTargets:
    def test_newer_guidance_format_blocks_all_writes(self, tmp_path: Path) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy", guidance_format=99)
        code = cli.main_upgrade(_deployment_args(dep.root, "--commit"))
        assert code == cli.EXIT_UNRESOLVED_MIGRATION
        # The signals target was migratable, but a blocker anywhere prevents ALL writes:
        assert signals_schema_version(dep.signals_db) is None

    def test_malformed_guidance_header_blocks(self, tmp_path: Path) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy")
        dep.guidance_doc.write_text("no header here\nentries: []\n", encoding="utf-8")
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == cli.EXIT_UNRESOLVED_MIGRATION

    def test_locked_encrypted_store_is_blocking_not_current(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy", locked_store=True)
        # A dry run observes the store as blocked (a blocking commit prints to stderr and
        # returns before emitting JSON, so the state is read from the dry-run report).
        assert cli.main_upgrade(_deployment_args(dep.root, "--json")) == 0
        payload = json.loads(capsys.readouterr().out)
        store = next(t for t in payload["operational_targets"] if t["kind"] == "assurance_sqlcipher")
        # An unreadable store is uninspectable — the state that gates the commit; it is never
        # allowed to read as "current".
        assert store["state"] == "uninspectable"
        # A commit is gated by that blocker and writes nothing to the migratable targets:
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == cli.EXIT_UNRESOLVED_MIGRATION
        assert dep.guidance_doc.read_text(encoding="utf-8").startswith("guidance_format: 1")
        assert signals_schema_version(dep.signals_db) is None


class TestAbsentStores:
    def test_absent_signals_store_is_no_target_and_is_never_created(self, tmp_path: Path) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy", with_signals=False)
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == 0
        # A fresh deployment never fabricates an absent store during a migration:
        assert not dep.signals_db.exists()


class TestPartialApplyAndResume:
    def test_injected_failure_after_a_commit_yields_partial_then_resumes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dep = build_previous_release_deployment(tmp_path / "deploy")

        # Guidance applies before signals (kind order), so the guidance target has already
        # committed when the injected signals failure lands.
        original_apply = signals_step._SignalsSnapshotSchemaStep.apply

        def _boom(self, view, uow, findings):  # type: ignore[no-untyped-def]
            raise RuntimeError("injected signals migration failure")

        monkeypatch.setattr(signals_step._SignalsSnapshotSchemaStep, "apply", _boom)
        code = cli.main_upgrade(_deployment_args(dep.root, "--commit", "--json"))
        assert code == cli.EXIT_PARTIAL_APPLY
        assert json.loads(capsys.readouterr().out)["outcome"] == "partial_apply"
        # The guidance target committed; the signals target rolled back whole:
        assert dep.guidance_doc.read_text(encoding="utf-8") == f"guidance_format: {GUIDANCE_FORMAT}\n{GUIDANCE_BODY}"
        assert signals_schema_version(dep.signals_db) is None

        # Resume: the failure removed, a rerun completes the remaining target idempotently.
        monkeypatch.setattr(signals_step._SignalsSnapshotSchemaStep, "apply", original_apply)
        assert cli.main_upgrade(_deployment_args(dep.root, "--commit")) == 0
        assert signals_schema_version(dep.signals_db) == SIGNALS_SCHEMA_VERSION


_CUSTOMIZED_GOAL_SCHEMA = '{\n  "type": "object",\n  "properties": {"operator_field": {"type": "string"}}\n}\n'
_ADDITIVE_SPECIALIZATIONS = (
    "specializations:\n"
    "  entity:\n"
    "    business-object:\n"
    "      - slug: invoice\n"
    "        name: Invoice\n"
    "        description: A customer invoice (declared by an earlier release)\n"
)


def _init_arch_repo(path: Path) -> None:
    """A git repo carrying an earlier-release ``.arch-repo/`` shape."""
    (path / ".arch-repo" / "schemata").mkdir(parents=True)
    # A schema an earlier release predates entirely (a newer release ships it) is absent, and
    # one the operator customized differs from the shipped default.
    (path / ".arch-repo" / "schemata" / "attributes.goal.schema.json").write_text(
        _CUSTOMIZED_GOAL_SCHEMA, encoding="utf-8"
    )
    # A specialization declaration in the earlier, additive shape: no `profiles:` binding.
    (path / ".arch-repo" / "specializations.yaml").write_text(
        _ADDITIVE_SPECIALIZATIONS, encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "earlier release"], cwd=path, check=True)


class TestRepositoryFormatEvolution:
    """An earlier-shape repository upgrades cleanly for the attribute-profile / AI-BOM
    format evolution: a newly-shipped default schema is added, an operator-customized schema
    is preserved, and an additive-shape specialization declaration still parses untouched."""

    def test_missing_default_schema_added_customized_preserved_declaration_untouched(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        _init_arch_repo(repo)
        code = cli.main_upgrade(["--repo-root", str(repo), "--commit"])
        assert code == 0
        # A newly shipped default the earlier release lacked is now present:
        assert (repo / ".arch-repo" / "schemata" / "attributes.resource.schema.json").is_file()
        # The operator's customization is never overwritten:
        assert (repo / ".arch-repo" / "schemata" / "attributes.goal.schema.json").read_text(
            encoding="utf-8"
        ) == _CUSTOMIZED_GOAL_SCHEMA
        # The additive-shape declaration still parses and is left byte-for-byte:
        assert (repo / ".arch-repo" / "specializations.yaml").read_text(
            encoding="utf-8"
        ) == _ADDITIVE_SPECIALIZATIONS
        # The repo records it has been evaluated against the current format contract:
        assert read_format_contract_version(repo) == FORMAT_CONTRACT_VERSION


_ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "entrypoint.sh"


class TestDockerStartupOrder:
    """The container entrypoint must migrate an existing (previous-release) deployment BEFORE
    it initializes any absent store and BEFORE it serves — otherwise Docker would start
    against a schema it never upgraded, or auto-create a store ahead of detection. This guards
    that ordering statically so an entrypoint edit that reorders it fails fast."""

    def test_entrypoint_upgrades_before_initializing_stores_and_serving(self) -> None:
        script = _ENTRYPOINT.read_text(encoding="utf-8")
        upgrade_at = script.index("arch-repair upgrade")
        init_absent_at = script.index("Initialize absent optional stores")
        serve_at = script.index("exec arch-backend")
        assert upgrade_at < init_absent_at < serve_at, (
            "entrypoint must run `arch-repair upgrade` before initializing absent stores and "
            "before `exec arch-backend`"
        )
