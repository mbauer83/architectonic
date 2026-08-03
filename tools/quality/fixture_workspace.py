"""A generated repository whose content is chosen so write walks have something to write against.

**Why this exists.** Three registers name work that is blocked on one artefact, and each says so in its
own source: 57 REST write operations never requested (`NEVER_REQUESTED_OPERATIONS`), 47 MCP write tools
never invoked (`WRITE_MOUNTS` in `tools/mcp/conformance.py`), 33 GUI port write methods never called
(`UNEXERCISED` in `readCoverage.conformance.test.ts`). All three talk to *one* backend process, so all
three need the same thing: a repository that may be written to and thrown away.

**Generated, not committed**, for two reasons. A third tracked model in the repository is a third
thing to keep verified, and — the better reason — building the fixture through the product's own write
tools makes the fixture *itself* a write round-trip. Every artifact below is authored by
`artifact_create_entity`, `artifact_add_connection`, `artifact_create_document` or
`artifact_create_diagram` with `dry_run=False`, through the same path an agent uses. If the write layer
is broken, generation fails; nothing is faked into place with `Path.write_text`.

The content list is a checklist rather than a sample, and it grows when a walk names a precondition it
cannot meet: the datatype diagram below arrived because two metadata PATCHes address a classifier and an
attribute, and nothing in the repository had either.

**Why this content and not more.** The dogfood repository is what the read walks run against today, and
what it happens to hold decides what they cover: `npm run conformance` passes 66/66 having only ever
seen `max_cvss_score: null`, `basis_snapshot_id: null`, `visibility_limited: false` — the *absent*
branch of every optional field. Exercising the populated branch needed a mock. So the content here is
a checklist rather than a sample: for each artifact kind, one instance with its optional fields
**present** and one with them **absent**; a collection that is **empty** and one that is **non-empty**;
an entity with **no connections** and one with connections in **both directions**. That list is
enumerable, which is why it is generated instead of curated.

Four frictions this removes, every one hit while writing the read walks: `previewDeleteEntity` needs an
*unreferenced* entity and currently probes rows hoping to find one; `previewMatrix` needs a real
connection between two entities to render anything; a delete round trip needs content it is allowed to
destroy; and specs that create content in the live repository depend on cleanup never failing, which is
how 247 lines leaked into `viewpoints.yaml`.

Usage — the workspace is disposable, so point a backend at it rather than at the real repository:

    uv run tools/quality/fixture_workspace.py --root /tmp/arch-fixture
    uv run arch-backend --repo-root /tmp/arch-fixture/engagements/ENG-FIXTURE/architecture-repository \\
        --port 8100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.workspace.engagement_repo_template import (  # noqa: E402
    ensure_arch_repo_defaults,
)

#: The engagement whose repository the fixture is. Named so a stray backend pointed at it is obvious.
ENGAGEMENT = "ENG-FIXTURE"

#: The throwaway secret that opens the fixture's credential vault. Not a secret in any real sense: the
#: vault it encrypts lives inside a temporary directory and is deleted with it. It exists so
#: `_get_backend` takes its documented headless branch instead of reaching for an OS keychain.
FIXTURE_MASTER_PASSWORD = "fixture-backend-throwaway"

#: The port the fixture's settings document declares, chosen so that nothing serves it.
#:
#: `arch-assurance unlock` ends with a best-effort POST of `{"authorize": true}` to
#: `http://localhost:{backend_port()}/api/assurance/reload`, and `backend_port()` falls back to
#: **8000** — the developer's own backend. A fixture that let that fall through would silently
#: authorize a foreign process while setting up its own store. Port 1 is privileged, so an ordinary
#: process cannot be listening there: "connection refused" is guaranteed rather than merely likely,
#: and the notification stays inside the fixture where there is nothing yet to notify.
_UNSERVED_PORT = 1

#: Every section the shipped `adr` schema requires. Written out rather than derived from
#: `BASE_DOCUMENT_SCHEMAS`, so a schema that gains a required section fails generation loudly here
#: instead of the fixture quietly acquiring a document the product would refuse.
_ADR_BODY = (
    "## Context\n\n{context}\n\n"
    "## Decision\n\n{decision}\n\n"
    "## Consequences\n\nNone: this document exists so a write walk has something to address.\n"
)


@dataclass(frozen=True)
class _AssuranceRoles:
    """What the fixture authored into the confidential store, addressed by role.

    Roles rather than positions, for the reason `application_diagram` records: `ids("node")[0]` was a
    positional accident waiting for a second node type. Each name below says what the thing is *for*,
    so a walk step declares the precondition it needs rather than an index into a list.
    """

    authored: dict[str, list[str]]

    def _one(self, role: str) -> str:
        ids = self.authored.get(role) or []
        if not ids:
            raise LookupError(
                f"the fixture authored no {role!r}. Either the store was not built or its content "
                "author was refused — see tools/quality/fixture_assurance_content.py"
            )
        return ids[0]

    @property
    def group(self) -> str:
        return self._one("assurance_group")

    @property
    def filed_analysis(self) -> str:
        """The analysis filed into `group` — what a group read has to be able to find."""
        return self._one("assurance_filed_analysis")

    @property
    def analysis(self) -> str:
        """The analysis filed nowhere, so "unfiled" is also a state the reads see."""
        return self._one("assurance_analysis")

    @property
    def hazard_node(self) -> str:
        """A node with every optional field present, and the one carrying the architecture ref."""
        return self._one("assurance_hazard_node")

    @property
    def bare_node(self) -> str:
        """A node with none of them, so the absent branch is read too."""
        return self._one("assurance_bare_node")

    @property
    def failure_mode(self) -> str:
        """The node an FMEA judgement is filed against; the only type that accepts one."""
        return self._one("assurance_failure_mode")

    @property
    def bound_node(self) -> str:
        """A control-structure node already bound to an architecture element.

        What nominates a row in the FMEA matrix: `fmea_rows.candidates` accepts an element only from a
        `binds-to` reference whose node is a control-structure node. The failure mode's own reference
        fills a cell in that row and cannot create one, so the matrix needs this node *and*
        `failure_mode`, both referencing the same element.
        """
        return self._one("assurance_bound_node")

    @property
    def bindable_node(self) -> str:
        """A control-structure node with `binding_status='unbound-pending'`.

        The subject model-and-bind exists for, and the only state it accepts: both the tool and the
        route refuse a node whose binding status is anything else, including the `unset` a plain create
        leaves behind.
        """
        return self._one("assurance_bindable_node")

    @property
    def edge(self) -> str:
        return self._one("assurance_edge")

    @property
    def edge_conn_type(self) -> str:
        """The connection type the ontology chose for that pair, not one this fixture named."""
        return self._one("assurance_edge_conn_type")

    @property
    def security_anchor(self) -> str:
        """The architecture entity the signals and the reference are attached to."""
        return self._one("assurance_security_anchor")

    @property
    def vulnerability(self) -> str:
        return self._one("assurance_vulnerability")

    @property
    def security_snapshot(self) -> str:
        return self._one("assurance_security_snapshot")

    @property
    def security_component(self) -> str:
        """The `SCM@…` id of the component the advisory is about — what *addresses* the resource.

        Not its purl. A purl identifies a package in a vocabulary another standard owns, and the same
        package arrives under different references from different feeds, so it filters the collection
        and does not address the row — see `_signals_routes.security_component`.
        """
        return self._one("assurance_security_component")

    @property
    def security_component_purl(self) -> str:
        """That same component's purl — what a VEX assessment is keyed by.

        A VEX assessment's key is (anchor, canonical component, canonical vulnerability), so this and
        `vulnerability` are a pair: an assessment naming a component with no finding is about nothing.
        """
        return self._one("assurance_security_component_purl")


@dataclass
class FixtureWorkspace:
    """What was built, and the ids a walk needs to address it."""

    root: Path
    engagement_root: Path
    enterprise_root: Path
    #: Kind -> ids authored, in creation order. A walk picks by role, never by position.
    authored: dict[str, list[str]] = field(default_factory=dict)

    def ids(self, kind: str) -> list[str]:
        return self.authored.get(kind, [])

    @property
    def unreferenced_entity(self) -> str:
        """An entity nothing points at — what a delete preview needs and cannot currently find."""
        return self.authored["unreferenced_entity"][0]

    @property
    def connected_entities(self) -> tuple[str, str]:
        """Two entities with a real connection between them — what a matrix preview needs."""
        source, target = self.authored["connected_entities"]
        return source, target

    @property
    def application_diagram(self) -> str:
        """The ArchiMate diagram over the two connected entities — what an edge label needs.

        Named by role, not taken from `ids("diagram")[0]`. That worked while there was one diagram and
        became a positional accident the moment a second kind arrived: `ids("diagram")` is the complete
        list, because that is what "served content is generated content" is checked against, and a walk
        wanting *this* diagram has to say so.
        """
        return self.authored["application_diagram"][0]

    @property
    def assurance(self) -> _AssuranceRoles:
        """The confidential store's content, by role.

        Grouped behind one accessor rather than spread across a dozen properties: the assurance
        content is a second authority with its own identifiers, and a walk step that reaches for
        `workspace.hazard_node` reads as though the repository held it.
        """
        return _AssuranceRoles(self.authored)

    @property
    def annotated_classifier(self) -> tuple[str, str, str]:
        """A datatype diagram, a classifier in it, and an attribute on that classifier.

        Three levels of identity, because that is what the deepest write address in the product names:
        `/api/diagrams/{id}/entities/{classifier}/attributes/{attribute}/metadata`. Being the fiddliest
        precondition to assemble is the likeliest reason nothing had ever requested it.
        """
        diagram, classifier, attribute = self.authored["annotated_classifier"]
        return diagram, classifier, attribute


def _roots(root: Path) -> tuple[Path, Path]:
    engagement = root / "engagements" / ENGAGEMENT / "architecture-repository"
    enterprise = root / "enterprise-repository"
    return engagement, enterprise


def state_dir(root: Path) -> Path:
    """Where a backend serving this workspace registers itself.

    Defined here rather than in `fixture_backend`, which is where it was first needed, because the
    *store builder* needs the same answer: an `arch-assurance` child that resolved its state directory
    from cwd would find the developer's `.arch/backend.pid` and address that process.
    `fixture_backend.state_dir_for` delegates here, so there is one definition of it.
    """
    return root / ".arch"


def assurance_settings_document(root: Path) -> Path:
    """The fixture's own settings document — never the repository's committed `config/settings.yaml`.

    `storage.assurance.activation_policy` is read from the settings document and from nowhere else,
    and CI sets it by mutating the committed file. A fixture must not: that file is shared, and its
    prose comments do not survive a rewrite.
    """
    return root / "config" / "settings.yaml"


def assurance_db_path(root: Path) -> Path:
    return root / ".arch-assurance" / "store.db"


def assurance_child_env(root: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """`base` (default `os.environ`) with every assurance seam pointed inside `root`.

    One definition and two kinds of caller — the `arch-assurance` children that build the store, and
    the backend child that serves it. They have to agree on all four: the credential *directory* is
    what makes the activation gate the builder writes the same gate the server reads, and two
    spellings of it would produce a store the server cannot open for a reason neither side reports.

    The forbid flag is **removed rather than overridden**. `tests/conftest.py` sets
    `ARCH_ASSURANCE_FORBID_REAL_CREDENTIAL_BACKEND` for the whole session and documents it as never
    unset; `_get_backend` checks it *before* the master-password branch and raises, so a child that
    inherited it would have no credential store at all rather than a throwaway one. Removing it here
    weakens nothing: this is a child's environment, and what the flag protects is the *developer's*
    keychain, which the two variables below have already moved out of reach.
    """
    from src.infrastructure.assurance._credential_store import _FORBID_REAL_BACKEND_ENV

    credentials = root / "credentials"
    credentials.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ if base is None else base)
    env.pop(_FORBID_REAL_BACKEND_ENV, None)
    env.update({
        "ARCH_SETTINGS_PATH": str(assurance_settings_document(root)),
        "ARCH_ASSURANCE_DB_PATH": str(assurance_db_path(root)),
        "ARCH_ASSURANCE_CREDENTIALS_DIR": str(credentials),
        "ARCH_ASSURANCE_MASTER_PASSWORD": FIXTURE_MASTER_PASSWORD,
        "ARCH_BACKEND_STATE_DIR": str(state_dir(root)),
    })
    return env


def fixture_child_env(root: Path, engagement: Path, enterprise: Path) -> dict[str, str]:
    """The complete environment for any child that must stay inside this fixture.

    The repository roots on top of `assurance_child_env`'s four assurance seams and the state
    directory. One definition for all three kinds of child — the `arch-assurance` CLI, the content
    author, and the served backend — because they have to agree about every one of them: the store
    they open, the vault holding its gate, the settings that decide whether it opens at all, and the
    repository whose entities its references point at.
    """
    return assurance_child_env(root, {
        **os.environ,
        "ARCH_REPO_ROOT": str(engagement),
        "ARCH_ENTERPRISE_ROOT": str(enterprise),
    })


def _python_child(root: Path, *args: str, what: str) -> str:
    """One `python -m …` child inside the fixture, loud on failure, stdout returned.

    Invoked as a module rather than by console-script name: `arch-assurance` is only on `PATH` inside
    `uv run`, and a walk started any other way would fail on a missing executable rather than on
    anything about the product.
    """
    import subprocess

    engagement, enterprise = _roots(root)
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        env=fixture_child_env(root, engagement, enterprise),
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"fixture: {what} failed: {detail}")
    return result.stdout


def _arch_assurance(root: Path, *args: str) -> str:
    """One `arch-assurance` command against the fixture, in a child process, loud on failure.

    **A child, not this process.** `init_store` writes a key, and `tests/conftest.py` forbids
    selecting a real credential backend for the whole session — so calling it here raises under
    pytest, and clearing that flag in a module this widely imported would be the fourth bypass of a
    guard whose own comment counts the first three. A child gets the flag removed and a throwaway
    vault instead, which is the same protection arrived at honestly.

    **The product's own CLI**, rather than reaching into `lifecycle` and `_credential_accounts`. With
    `ARCH_SETTINGS_PATH` and `--db-path` supplied it resolves the *fixture's* paths throughout, so
    this is the adopter's real path rather than a re-implementation of it — and the settings document
    ends up written by the writer that owns its schema.

    Invoked as a module rather than by console-script name: `arch-assurance` is only on `PATH` inside
    `uv run`, and a walk started any other way would fail on a missing executable rather than on
    anything about the product.
    """
    return _python_child(
        root, "src.infrastructure.cli.arch_assurance", *args,
        what=f"arch-assurance {' '.join(args)}",
    )


def _build_assurance_store(root: Path) -> None:
    """Create the fixture's confidential assurance store and activate it for an unattended process.

    Four steps, in this order, each of which the next one needs:

    1. the settings document, so every child below resolves the fixture's configuration and not the
       repository's — and so `unlock`'s notification cannot address the developer's backend
       (`_UNSERVED_PORT`);
    2. `init`, which creates the encrypted store and writes its key to the scoped account;
    3. `use-backend … --activation-policy persistent`, because `init` writes the backends but leaves
       the policy at its `manual` default, under which a newly started process opens nothing and every
       assurance route answers **423**;
    4. `unlock`, which writes the `setup-confirmed` activation gate. Still required under
       `persistent`: that policy skips the *per-process* authorization check, and the gate is read
       immediately afterwards — `store_factory` is fail-closed on an absent confirmation.

    All of it before any backend starts. `_inject_capability_sentinels` runs at bootstrap, so a store
    created after the server booted is a store the server's capability sentinels do not know about.
    """
    import yaml

    settings = assurance_settings_document(root)
    settings.parent.mkdir(parents=True, exist_ok=True)
    document = yaml.dump({"backend": {"port": _UNSERVED_PORT}}, default_flow_style=False)
    # `yaml.dump` returns a `str` when given no stream, but its stub says `str | bytes | None` — and
    # writing an empty document here would fail *open*: `backend_port()` would go back to its 8000
    # default, which is the developer's backend. Checked rather than coerced with `or ""`.
    if not isinstance(document, str):
        raise RuntimeError(f"fixture: yaml.dump produced {type(document).__name__}, not a document")
    settings.write_text(document, encoding="utf-8")

    db_path = assurance_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _arch_assurance(root, "--db-path", str(db_path), "init")
    _arch_assurance(root, "use-backend", "sqlcipher", "--activation-policy", "persistent")
    _arch_assurance(root, "--db-path", str(db_path), "unlock")


def _author_assurance_content(root: Path, *, anchor: str) -> dict[str, list[str]]:
    """The analyses, nodes, edge, reference, signals and judgement a read walk needs to read.

    A child for the same reason the store's creation is one, and the ids come back as JSON because
    the store decides them — the same shape as `_datatype_diagram`, which reads back the classifier id
    the write tool minted rather than assuming the one it asked for.
    """
    stdout = _python_child(
        root, "tools.quality.fixture_assurance_content", "--anchor", anchor,
        what="authoring assurance content",
    )
    roles = json.loads(stdout)
    if not isinstance(roles, dict) or not roles:
        raise RuntimeError(f"fixture: the assurance content author reported nothing: {stdout!r}")
    return {str(role): [str(i) for i in ids] for role, ids in roles.items()}


def _git(repo: Path, *args: str) -> None:
    """One git command against `repo`, loud on failure.

    Loud because a half-initialised repository is worse than none: the sync operations would then fail
    for a reason ("not a git repository", "no upstream") that reads as a product defect.
    """
    import subprocess

    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(repo), *args],  # noqa: S607 - git from PATH is the product's own assumption
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"fixture: git {' '.join(args)} in {repo} failed: {result.stderr.strip()}")


def _init_git(repo: Path, remote: Path) -> None:
    """Make `repo` a git repository whose current branch has an upstream it may push to.

    Three things the sync operations need and a directory does not have. `ensure_working_branch` runs
    `checkout -b`, which needs a commit to branch from; `commit_engagement_work` refuses when there is
    nothing uncommitted, so the fixture's generated content is committed here and the *walk's* writes
    are what it later saves; and `push_engagement` runs a bare `git push`, which needs an upstream.

    The remote is a bare repository beside the workspace, so a push has somewhere real to go and no
    network is involved. `GIT_CONFIG_GLOBAL=/dev/null` in `_git` keeps the developer's own git config —
    signing keys, hooks, `push.default` — out of it: a fixture that failed because someone's global
    config demanded a GPG signature would be reporting the developer's machine, not the product.
    """
    remote.parent.mkdir(parents=True, exist_ok=True)
    _git(remote.parent, "init", "--bare", "--initial-branch=main", remote.name)

    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Fixture Generator")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Fixture content as generated")
    _git(repo, "push", "-u", "origin", "main")


def _prepare_roots(root: Path) -> tuple[Path, Path]:
    """Create both roots with current `.arch-repo` defaults.

    `ensure_arch_repo_defaults` rather than `arch-init`: the latter wants a git remote and an
    `arch-workspace.yaml`, which a throwaway fixture has no use for, and it is the same function the
    product runs to bring a repository up to current defaults — so the fixture starts life in the state
    a real repository is repaired into, not in an invented one.
    """
    engagement, enterprise = _roots(root)
    for path in (engagement, enterprise):
        (path / "model").mkdir(parents=True, exist_ok=True)
        ensure_arch_repo_defaults(path)
    return engagement, enterprise


def _wrote(result: dict[str, Any], what: str) -> str:
    """Take the artifact id from a write, failing loudly when the write was refused.

    A refusal arrives as `wrote: false` inside a *success* — the verification is attached rather than
    raised — so a generator that only checked for an exception would build an empty workspace and
    report success. That is the failure mode this whole exercise is about.
    """
    if not result.get("wrote"):
        raw = result.get("verification")
        verification: dict[str, Any] = raw if isinstance(raw, dict) else {}
        issues: Any = verification.get("issues") or result.get("errors") or []
        raise RuntimeError(f"fixture: {what} was not written: {issues or result}")
    identifier = result.get("artifact_id")
    if not isinstance(identifier, str):
        raise RuntimeError(f"fixture: {what} reported no artifact_id: {result}")
    return identifier


def build_fixture_workspace(root: Path) -> FixtureWorkspace:
    """Author the checklist through the product's write tools. Idempotent per root only if empty."""
    from src.infrastructure.mcp import mcp_artifact_server as write

    engagement, enterprise = _prepare_roots(root)
    where = str(engagement)
    authored: dict[str, list[str]] = {}

    def record(kind: str, identifier: str) -> str:
        authored.setdefault(kind, []).append(identifier)
        return identifier

    # ── Entities: optional fields present, then absent ───────────────────────────────────────────
    populated = record(
        "entity",
        _wrote(
            write.artifact_create_entity(
                artifact_type="application-component",
                name="Fixture Populated Component",
                summary="Every optional field carries a value, so a decoder meets the present branch.",
                properties={"lifecycle_state": "active"},
                notes="Authored by the fixture generator.",
                keywords=["fixture", "populated"],
                status="draft",
                dry_run=False,
                repo_root=where,
            ),
            "populated entity",
        ),
    )
    sparse = record(
        "entity",
        _wrote(
            write.artifact_create_entity(
                artifact_type="application-component",
                name="Fixture Sparse Component",
                dry_run=False,
                repo_root=where,
            ),
            "sparse entity",
        ),
    )
    # Nothing will point at this one, which is what a delete preview needs and cannot currently find.
    record(
        "unreferenced_entity",
        _wrote(
            write.artifact_create_entity(
                artifact_type="application-component",
                name="Fixture Unreferenced Component",
                dry_run=False,
                repo_root=where,
            ),
            "unreferenced entity",
        ),
    )

    # ── A connection, so the graph is non-empty and a matrix has something to render ─────────────
    record("connection", _wrote(
        write.artifact_add_connection(
            source_entity=populated,
            connection_type="archimate-serving",
            target_entity=sparse,
            description="A real edge, so neighbourhood and matrix reads have a non-empty answer.",
            dry_run=False,
            repo_root=where,
        ),
        "connection",
    ))
    authored["connected_entities"] = [populated, sparse]

    # ── Documents: one with optional frontmatter and keywords, one with neither ──────────────────
    record("document", _wrote(
        write.artifact_create_document(
            doc_type="adr",
            title="Fixture Decision With Everything",
            body=_ADR_BODY.format(context="A populated document.", decision="Carry every optional field."),
            keywords=["fixture", "populated"],
            dry_run=False,
            repo_root=where,
        ),
        "populated document",
    ))
    record("document", _wrote(
        write.artifact_create_document(
            doc_type="adr",
            title="Fixture Decision Without Extras",
            body=_ADR_BODY.format(context="A sparse document.", decision="Omit every optional field."),
            dry_run=False,
            repo_root=where,
        ),
        "sparse document",
    ))

    # ── A diagram, so diagram reads and the render path have a subject ───────────────────────────
    authored["application_diagram"] = [record("diagram", _wrote(
        write.artifact_create_diagram(
            diagram_type="archimate-application",
            name="Fixture Application View",
            entity_ids=[populated, sparse],
            dry_run=False,
            repo_root=where,
        ),
        "diagram",
    ))]

    # ── A datatype diagram, for the two metadata writes that address three levels deep ───────────
    annotated = _datatype_diagram(write, where)
    authored["annotated_classifier"] = list(annotated)
    # Also a diagram, and `ids("diagram")` is what "served content is generated content" is checked
    # against — so a diagram known only by its specialised role would make that check fail on a
    # diagram the fixture itself authored.
    record("diagram", annotated[0])

    # ── The confidential store and its content, before git and before any backend ─────────────────
    # Before git so its key and vault are not committed into the fixture's own history; before any
    # backend because the capability sentinels are injected at bootstrap.
    _build_assurance_store(root)
    # `populated` rather than any entity: the anchor has to be one the reads can join back to, and an
    # entity carrying its optional fields is the one whose lens and security answers are non-empty.
    authored.update(_author_assurance_content(root, anchor=populated))

    # ── Git, last: the content has to exist before there is anything to commit ────────────────────
    _init_git(engagement, root / "remotes" / "engagement.git")
    _init_git(enterprise, root / "remotes" / "enterprise.git")

    return FixtureWorkspace(
        root=root, engagement_root=engagement, enterprise_root=enterprise, authored=authored
    )


#: The attribute's id is the caller's to choose and is kept verbatim; the classifier's is *generated*,
#: which is why the diagram has to be read back below rather than assumed.
_ATTRIBUTE_ID = "attr_placed_at"


def _datatype_diagram(write: Any, where: str) -> tuple[str, str, str]:
    """Author a datatype diagram with one classifier carrying one attribute, and say what they are.

    The classifier id cannot be predicted: `artifact_create_diagram` replaces the label-derived id the
    caller supplies with a generated `CLF@…`, which is correct — a classifier is an artifact and gets
    an artifact's identity. So the diagram is read back through the product's own diagram parser. That
    is not hand-editing a model file: the content was authored by the write tool, and this reads what
    the tool decided rather than deciding it here.
    """
    from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

    result = write.artifact_create_diagram(
        diagram_type="datatype",
        name="Fixture Annotated Types",
        diagram_entities={
            "classifier": [
                {
                    "id": "clf_fixture_order",
                    "label": "Fixture Order",
                    "kind": "entity",
                    "attributes": [
                        {
                            "id": _ATTRIBUTE_ID,
                            "name": "placed_at",
                            "type": {"kind": "primitive", "name": "DateTime"},
                        }
                    ],
                }
            ]
        },
        dry_run=False,
        repo_root=where,
    )
    diagram_id = _wrote(result, "datatype diagram")

    path = result.get("path")
    if not isinstance(path, str):
        raise RuntimeError(f"fixture: datatype diagram reported no path: {result}")
    classifiers = parse_diagram_file(Path(path)).frontmatter.get("diagram-entities", {})
    rows = classifiers.get("classifier") if isinstance(classifiers, dict) else None
    if not rows:
        raise RuntimeError(f"fixture: the datatype diagram at {path} carries no classifier")
    classifier_id = rows[0].get("id")
    if not isinstance(classifier_id, str):
        raise RuntimeError(f"fixture: the classifier in {path} has no id: {rows[0]}")
    return diagram_id, classifier_id, _ATTRIBUTE_ID


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, type=Path, help="directory to build the workspace in")
    args = parser.parse_args(argv)

    workspace = build_fixture_workspace(args.root)
    print(f"fixture workspace at {workspace.root}")
    print(f"  engagement: {workspace.engagement_root}")
    print(f"  enterprise: {workspace.enterprise_root}")
    for kind, ids in sorted(workspace.authored.items()):
        print(f"  {kind}: {len(ids)}")
        for identifier in ids:
            print(f"    {identifier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
