"""Refreshing a real diagram must not silently drop what it draws.

`diagram_sync`'s own contract says a refresh "never silently deletes or blanks a diagram", and
nothing held it to that. It was broken: the reconcile path rebuilds the binding set by reading
relations out of the PUML body, using a parser that recognised only macro calls and
stereotype-labelled arrows — while the renderer emits bare arrows. A generated body therefore
declared nothing, so any relation drawn but not already bound was deleted on the next refresh, and
`removed_connection_ids` stayed empty because it only reports relations that were *recognised* and
then failed to resolve. Six `archimate-influence` relations were lost from one motivation view that
way, and `artifact_verify` reported the repository clean throughout.

The invariant is stated over the **body**, not the frontmatter, and that distinction is the whole
test. Comparing binding sets passes even with the defect reinstated: inference returning nothing
leaves the existing `connection-ids-used` untouched, so nothing looks dropped while arrows vanish
from the picture. What must be preserved is that every relation the diagram *expresses* still is —
as an arrow, or as the visual nesting that composition and aggregation are drawn with.

Run against the shipped repository rather than a fixture, because the defect lived in how the real
renderer's output met the real parser; a fixture written by the same hand as the parser would have
agreed with it. Nothing is written: every refresh here is a dry run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = (
    REPO_ROOT / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"
    / "diagram-catalog" / "diagrams"
)

_ARROW_RE = re.compile(
    r"^(?P<src>[A-Za-z0-9_-]+)\s+(?P<arrow>[-.*|o<>][^\s]*[-.*|o<>])\s+(?P<tgt>[A-Za-z0-9_-]+)"
)
#: `rectangle "…" <<stereo>> as ALIAS {`  — a container opening.
_CONTAINER_RE = re.compile(r"\bas\s+(?P<alias>[A-Za-z0-9_-]+)\s*\{\s*$")
#: `rectangle "…" <<stereo>> as ALIAS`  — a leaf declaration.
_LEAF_RE = re.compile(r"\bas\s+(?P<alias>[A-Za-z0-9_-]+)\s*$")


def _body(text: str) -> str:
    """The PUML body, without the YAML frontmatter."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def _arrows(text: str) -> set[tuple[str, str]]:
    """Every (source, target) alias pair the body draws as an arrow. Hidden links excluded — they
    position elements and assert nothing about the model."""
    pairs: set[tuple[str, str]] = set()
    for raw in _body(text).splitlines():
        line = raw.strip()
        if not line or line.startswith(("'", "!", "skinparam", "sprite", "title", "@")):
            continue
        match = _ARROW_RE.match(line)
        if match is not None and "[hidden]" not in match.group("arrow"):
            pairs.add((match.group("src"), match.group("tgt")))
    return pairs


def _nesting(text: str) -> set[tuple[str, str]]:
    """(parent, child) alias pairs the body expresses by containment.

    Read from both sides, because PlantUML draws composition and aggregation as containment: a body
    can assert a relation with no arrow at all. Reading only arrows is what let a refresh flatten
    `reverse-architecture-architecture-conformance-review` — its functions were nested inside the
    processes that orchestrate them, and losing that read as "no change" to a test comparing arrows.

    A grouping rectangle contributes no parent: the generated form carries no alias, and an authored
    one is recognised by its `CommonGrouping` stereotype. Otherwise every member of a group would
    look like a child of it.
    """
    pairs: set[tuple[str, str]] = set()
    stack: list[str] = []
    for raw in _body(text).splitlines():
        line = raw.strip()
        if not line or line.startswith(("'", "!", "skinparam", "sprite", "title", "@")):
            continue
        if line == "}":
            if stack:
                stack.pop()
            continue
        container = _CONTAINER_RE.search(line)
        if container is not None and "CommonGrouping" not in line:
            alias = container.group("alias")
            if stack and stack[-1]:
                pairs.add((stack[-1], alias))
            stack.append(alias)
            continue
        if line.endswith("{"):
            stack.append("")
            continue
        leaf = _LEAF_RE.search(line)
        if leaf is not None and stack and stack[-1]:
            pairs.add((stack[-1], leaf.group("alias")))
    return pairs


def _used(text: str, key: str) -> set[str]:
    """Values of a top-level frontmatter list field (`entity-ids-used`, …)."""
    out: set[str] = set()
    collecting = False
    for line in text.splitlines():
        if line.strip() == "---" and collecting:
            break
        if line.startswith(f"{key}:"):
            collecting = True
            continue
        if collecting:
            if line.startswith("- "):
                out.add(line[2:].strip())
            elif line and not line[0].isspace():
                collecting = False
    return out


def _diagram_ids() -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for path in sorted(CATALOG.rglob("*.puml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("artifact-id:"):
                found.append((line.split(":", 1)[1].strip(), path))
                break
    return found


DIAGRAMS = _diagram_ids()

pytestmark = pytest.mark.skipif(not DIAGRAMS, reason="no engagement diagram catalog in this checkout")


@pytest.fixture(scope="module")
def refreshed() -> dict[str, dict[str, Any]]:
    """Every diagram's dry-run refresh, computed once for the whole module."""
    from src.infrastructure.mcp.artifact_mcp.edit_tools import artifact_edit_diagram

    return {
        artifact_id: artifact_edit_diagram(artifact_id=artifact_id, puml="auto-sync", dry_run=True)
        for artifact_id, _ in DIAGRAMS
    }


@pytest.mark.parametrize("artifact_id,path", DIAGRAMS, ids=[a for a, _ in DIAGRAMS])
def test_refresh_keeps_every_relation_the_diagram_draws(
    artifact_id: str, path: Path, refreshed: dict[str, dict[str, Any]],
) -> None:
    """A relation drawn today is still expressed after a refresh — or is named in
    `removed_connection_ids`. Those are the only two honest outcomes; disappearing quietly is the
    defect this test exists for."""
    result = refreshed[artifact_id]
    content = result.get("content")
    if not isinstance(content, str):
        pytest.skip(f"{artifact_id}: refresh produced no content ({sorted(result)})")

    # Both forms on both sides: a relation may be drawn as an arrow or as containment, and may
    # legitimately change from one to the other across a refresh without being lost.
    stored = path.read_text(encoding="utf-8")

    # Mirror what the reconcile does: an alias that resolves to no entity carries no relation. A
    # grouping the author aliased (`GRP_PERFORMED`) is exactly that — it names a box, not an element.
    def entity_aliases(text: str) -> set[str]:
        segments = {eid.split(".")[1] for eid in _used(text, "entity-ids-used") if eid.count(".") >= 2}
        return segments

    known = entity_aliases(stored) | entity_aliases(content)

    def only_entities(pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
        return {
            (src, tgt) for src, tgt in pairs
            if src.split("_", 1)[-1] in known and tgt.split("_", 1)[-1] in known
        }

    before = only_entities(_arrows(stored) | _nesting(stored))
    after = only_entities(_arrows(content) | _nesting(content))
    # A report names model ids; the body names aliases. An alias is the id's random segment, so a
    # reported drop is matched by either endpoint segment appearing in it.
    reported = " ".join(str(c) for c in (result.get("removed_connection_ids") or []))

    def is_reported(pair: tuple[str, str]) -> bool:
        src_seg = pair[0].split("_", 1)[-1]
        tgt_seg = pair[1].split("_", 1)[-1]
        return src_seg in reported and tgt_seg in reported

    lost = {pair for pair in before - after if not is_reported(pair)}
    assert not lost, (
        f"{artifact_id}: refresh stopped expressing {len(lost)} relation(s) and reported none of "
        f"them: {sorted(lost)}"
    )


@pytest.mark.parametrize("artifact_id,path", DIAGRAMS, ids=[a for a, _ in DIAGRAMS])
def test_refresh_keeps_every_entity_the_diagram_uses_or_reports_it(
    artifact_id: str, path: Path, refreshed: dict[str, dict[str, Any]],
) -> None:
    result = refreshed[artifact_id]
    content = result.get("content")
    if not isinstance(content, str):
        pytest.skip(f"{artifact_id}: refresh produced no content")

    def used(text: str) -> set[str]:
        out: set[str] = set()
        collecting = False
        for line in text.splitlines():
            if line.strip() == "---" and collecting:
                break
            if line.startswith("entity-ids-used:"):
                collecting = True
                continue
            if collecting:
                if line.startswith("- "):
                    out.add(line[2:].strip())
                elif line and not line[0].isspace():
                    collecting = False
        return out

    reported = {str(e) for e in (result.get("removed_entity_ids") or [])}
    unexplained = used(path.read_text(encoding="utf-8")) - used(content) - reported
    assert not unexplained, (
        f"{artifact_id}: refresh dropped used entities without reporting them: {sorted(unexplained)}"
    )


@pytest.fixture(scope="module")
def completeness_context() -> dict[str, Any]:
    """Registry and catalogs for running the completeness rule over the live catalog."""
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    catalogs = build_runtime_catalogs(build_module_registry())
    engagement_root = REPO_ROOT / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"
    return {
        "registry": ArtifactRegistry(shared_artifact_index(engagement_root)),
        "stereotype_map": catalogs.ontology.archimate_stereotype_to_connection_type(),
        "diagram_types": catalogs.diagram_types,
    }


@pytest.mark.parametrize("artifact_id,path", DIAGRAMS, ids=[a for a, _ in DIAGRAMS])
def test_every_relation_a_stored_diagram_expresses_is_bound(
    artifact_id: str, path: Path, completeness_context: dict[str, Any],
) -> None:
    """The other half of "loses nothing": before any refresh runs, the stored bindings must
    already own everything the stored body expresses (§4.3 completeness invariant, E314–E317).
    A diagram that draws more than it binds is data loss waiting — the reconcile treats the
    binding set as authoritative — and verification has to say so while the divergence is
    still repairable. Invariant, not a count: authoring new diagrams must never break this."""
    import yaml

    from src.application.verification._verifier_rules_puml_completeness import (
        check_diagram_relation_completeness,
    )
    from src.application.verification.artifact_verifier_types import VerificationResult

    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    fm = yaml.safe_load(text[3:end]) or {}
    result = VerificationResult(path=path, file_type="diagram")
    check_diagram_relation_completeness(
        _body(text), fm, completeness_context["registry"], result, str(path),
        stereotype_map=completeness_context["stereotype_map"],
        diagram_type_catalog=completeness_context["diagram_types"],
    )
    assert not result.issues, (
        f"{artifact_id}: body expresses relations its bindings disown: "
        f"{[f'{i.code}: {i.message}' for i in result.issues]}"
    )
