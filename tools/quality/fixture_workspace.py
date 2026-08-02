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


def _roots(root: Path) -> tuple[Path, Path]:
    engagement = root / "engagements" / ENGAGEMENT / "architecture-repository"
    enterprise = root / "enterprise-repository"
    return engagement, enterprise


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
    record("diagram", _wrote(
        write.artifact_create_diagram(
            diagram_type="archimate-application",
            name="Fixture Application View",
            entity_ids=[populated, sparse],
            dry_run=False,
            repo_root=where,
        ),
        "diagram",
    ))

    return FixtureWorkspace(
        root=root, engagement_root=engagement, enterprise_root=enterprise, authored=authored
    )


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
