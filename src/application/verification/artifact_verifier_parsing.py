from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.application.verification.artifact_verifier_types import (
    ConnectionRefs,
    Issue,
    Severity,
    VerificationResult,
)
from src.domain.repository.connection_declaration import parse_connection_header
from src.domain.repository.frontmatter import Frontmatter, FrontmatterProblem, opens_with_frontmatter, read_frontmatter
from src.domain.yaml_documents import parse_yaml

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot


def read_file(
    path: Path, result: VerificationResult, loc: str, *, snapshot: "RepositorySnapshot | None" = None
) -> str | None:
    """The file's content, from the pass's snapshot when there is one.

    A whole-repository pass reads every file once, under exclusivity, and then evaluates rules from
    that byte-image with no lock held — so a rule that reached back to the filesystem would observe a
    state the rest of the pass did not, and the report would describe neither. `snapshot` is threaded
    rather than stored because one verifier instance serves concurrent requests.

    A path the snapshot does not hold falls back to disk: single-file verification passes no
    snapshot at all, and a document outside the inventory is read the same way it always was.
    """
    if snapshot is not None and (content := snapshot.read(path)) is not None:
        return content
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        result.issues.append(Issue(Severity.ERROR, "E001", f"Cannot read file: {exc}", loc))
        return None


def parse_frontmatter_from_path(path: Path) -> dict | None:
    try:
        content = path.read_text(encoding="utf-8")
        return extract_yaml_block(content)
    except Exception:
        return None


def extract_yaml_block(content: str) -> dict | None:
    match read_frontmatter(content):
        case Frontmatter(text=text):
            return parse_yaml(text) or {}
        case _:
            return None


#: Which diagnostic each missing fence is. A table rather than two branches, so the pair stays visibly
#: exhaustive against `FrontmatterProblem` instead of being spread through the control flow.
_MISSING_FENCE_ISSUE: dict[FrontmatterProblem, tuple[str, str]] = {
    FrontmatterProblem.NO_OPENING_FENCE: ("E011", "File does not begin with YAML frontmatter (--- block)"),
    FrontmatterProblem.NO_CLOSING_FENCE: ("E012", "Frontmatter opening --- has no closing ---"),
}


def parse_frontmatter(content: str, result: VerificationResult, loc: str) -> dict | None:
    reading = read_frontmatter(content)
    if isinstance(reading, FrontmatterProblem):
        code, message = _MISSING_FENCE_ISSUE[reading]
        result.issues.append(Issue(Severity.ERROR, code, message, loc))
        return None

    yaml_block = reading.text
    try:
        fm = parse_yaml(yaml_block)
    except yaml.YAMLError as exc:
        result.issues.append(Issue(Severity.ERROR, "E013", f"Frontmatter YAML parse error: {exc}", loc))
        return None

    if not isinstance(fm, dict):
        result.issues.append(Issue(Severity.ERROR, "E014", "Frontmatter is not a YAML mapping", loc))
        return None

    return fm


def parse_puml_frontmatter(content: str, result: VerificationResult, loc: str) -> dict | None:
    """Parse YAML frontmatter from a PUML file.

    Supports standard ``---`` delimited YAML frontmatter before ``@startuml``.
    """
    # Standard YAML frontmatter (--- ... ---)
    if opens_with_frontmatter(content):
        return parse_frontmatter(content, result, loc)

    result.issues.append(
        Issue(
            Severity.ERROR,
            "E311",
            "PUML file has no YAML frontmatter (expected --- block before @startuml)",
            loc,
        )
    )
    return None


def extract_puml_frontmatter_best_effort(content: str) -> dict | None:
    """Best-effort extraction of YAML frontmatter from a PUML file."""
    if opens_with_frontmatter(content):
        return extract_yaml_block(content)
    return None


def parse_connection_refs(path: Path) -> ConnectionRefs | None:
    """Parse connection references from an .outgoing.md file.

    Returns a ``ConnectionRefs`` with source-entity as source_ids and all
    target entities (from ``### conn-type → target-id`` headers) as target_ids.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = extract_yaml_block(content)
    if fm is None:
        return None

    source = fm.get("source-entity", "")
    srcs = [str(source)] if source else []

    tgts: list[str] = []
    # Through the owner of the section grammar rather than by splitting on the arrow here: the
    # multiplicity stripping this replaces was the third copy of the same seven lines, and a copy is
    # where "conn-type [src] → [tgt] target" stops meaning the same thing in two places.
    for line in content.splitlines():
        if line.startswith("### "):
            declaration = parse_connection_header(line[4:])
            if declaration is not None:
                tgts.append(declaration.target_id)

    return ConnectionRefs(
        source_ids=tuple(srcs),
        target_ids=tuple(tgts),
    )


def parse_diagram_refs(path: Path) -> dict[str, list[str]] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if path.suffix == ".puml":
        fm = extract_puml_frontmatter_best_effort(content)
    else:
        fm = extract_yaml_block(content)
    if not isinstance(fm, dict):
        return None

    entity_ids_raw = fm.get("entity-ids-used")
    conn_ids_raw = fm.get("connection-ids-used")
    entity_ids = [str(x) for x in entity_ids_raw] if isinstance(entity_ids_raw, list) else []
    connection_ids = [str(x) for x in conn_ids_raw] if isinstance(conn_ids_raw, list) else []
    return {"entity_ids": entity_ids, "connection_ids": connection_ids}
