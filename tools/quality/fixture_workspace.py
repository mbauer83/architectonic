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
import os
import sys
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

#: Every section the shipped `adr` schema requires. Written out rather than derived from
#: `BASE_DOCUMENT_SCHEMAS`, so a schema that gains a required section fails generation loudly here
#: instead of the fixture quietly acquiring a document the product would refuse.
_ADR_BODY = (
    "## Context\n\n{context}\n\n"
    "## Decision\n\n{decision}\n\n"
    "## Consequences\n\nNone: this document exists so a write walk has something to address.\n"
)


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
