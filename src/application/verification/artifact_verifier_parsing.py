from pathlib import Path

import yaml

from src.application.verification.artifact_verifier_types import (
    ConnectionRefs,
    Issue,
    Severity,
    VerificationResult,
)


def read_file(path: Path, result: VerificationResult, loc: str) -> str | None:
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
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    return yaml.safe_load(content[3:end].strip()) or {}


def parse_frontmatter(content: str, result: VerificationResult, loc: str) -> dict | None:
    if not content.startswith("---"):
        result.issues.append(
            Issue(Severity.ERROR, "E011", "File does not begin with YAML frontmatter (--- block)", loc)
        )
        return None

    end = content.find("\n---", 3)
    if end == -1:
        result.issues.append(Issue(Severity.ERROR, "E012", "Frontmatter opening --- has no closing ---", loc))
        return None

    yaml_block = content[3:end].strip()
    try:
        fm = yaml.safe_load(yaml_block)
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
    if content.startswith("---"):
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
    if content.startswith("---"):
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
    for line in content.splitlines():
        if line.startswith("### ") and " → " in line:
            header = line[4:].strip()
            # Handle optional multiplicities: "conn-type [src] → [tgt] target_id"
            after_arrow = header.split(" → ", 1)[1].strip()
            # Strip optional target multiplicity "[tgt_mult] " prefix
            if after_arrow.startswith("["):
                bracket_end = after_arrow.find("]")
                if bracket_end != -1:
                    after_arrow = after_arrow[bracket_end + 1 :].lstrip()
            tgts.append(after_arrow)

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
