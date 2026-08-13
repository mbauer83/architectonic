import re
from pathlib import Path

from src.application.artifacts.parsing import extract_declared_puml_aliases as _extract_declared_puml_aliases_shared
from src.application.verification._verifier_rules_puml_relations import (
    _extract_entity_display_alias,
    _normalize_puml_alias,
)
from src.application.verification.artifact_verifier_types import (
    DIAGRAM_ARTIFACT_TYPES,
    ENTITY_ID_RE,
    Issue,
    Severity,
    VerificationResult,
    entity_id_from_path,
)
from src.domain.repository.repo_layout import MODEL


def check_required_fields(fm: dict, required: frozenset[str], result: VerificationResult, loc: str) -> None:
    for field_name in sorted(required):
        if field_name not in fm or fm[field_name] is None:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E021",
                    f"Required frontmatter field '{field_name}' is missing or null",
                    loc,
                )
            )


def check_artifact_id_entity(fm: dict, result: VerificationResult, loc: str) -> None:
    if "artifact-id" not in fm:
        return
    aid = str(fm["artifact-id"])
    if not ENTITY_ID_RE.match(aid):
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E101",
                f"artifact-id '{aid}' does not match TYPE@epoch.random.name pattern",
                loc,
            )
        )
        return

    file_id = entity_id_from_path(result.path)
    if file_id != aid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E104",
                f"entity filename stem '{file_id}' does not match artifact-id '{aid}'",
                loc,
            )
        )


def check_artifact_type(
    fm: dict,
    valid: frozenset[str],
    label: str,
    result: VerificationResult,
    loc: str,
) -> None:
    if "artifact-type" not in fm:
        return
    artifact_type = str(fm["artifact-type"])
    if artifact_type not in valid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E102",
                f"artifact-type '{artifact_type}' is not a recognised {label}",
                loc,
            )
        )


def check_enum(
    fm: dict,
    field_name: str,
    valid: frozenset[str],
    result: VerificationResult,
    loc: str,
) -> None:
    if field_name not in fm or fm[field_name] is None:
        return
    value = str(fm[field_name])
    if value not in valid:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E022",
                (f"Field '{field_name}' has invalid value '{value}'; expected one of: {sorted(valid)}"),
                loc,
            )
        )


def check_section(
    content: str,
    section: str,
    *,
    required: bool,
    result: VerificationResult,
    loc: str,
) -> None:
    marker = f"<!-- {section} -->"
    if marker in content:
        return
    severity = Severity.ERROR if required else Severity.WARNING
    code = "E031" if required else "W031"
    msg = f"Section marker '{marker}' is {'absent' if required else 'absent (optional for connections)'}"
    result.issues.append(Issue(severity, code, msg, loc))


def check_puml_structure(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    if "@startuml" not in content:
        result.issues.append(Issue(Severity.ERROR, "E304", "@startuml marker is missing", loc))
    if "@enduml" not in content:
        result.issues.append(Issue(Severity.ERROR, "E305", "@enduml marker is missing", loc))

    body_lines = [line for line in content.splitlines() if not line.lstrip().startswith("'")]
    has_visible_title = any(re.match(r"^\s*title(\s|$)", line, flags=re.IGNORECASE) for line in body_lines)
    if not has_visible_title:
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E308",
                "Diagram must include a visible title line (for example: 'title <diagram name>')",
                loc,
            )
        )

    diagram_type = str(fm.get("diagram-type", ""))
    if "archimate" in diagram_type or "usecase" in diagram_type:
        has_stereotypes = "_archimate-stereotypes.puml" in content
        has_inlined_archimate = (
            "skinparam rectangle<<" in content and "hide stereotype" in content
        ) or "sprite $archimate_" in content
        has_inline_declarations = bool(
            re.search(r'rectangle\s+"[^"]*"\s+<<\w+>>', content)
        )
        if not has_stereotypes and not has_inlined_archimate and not has_inline_declarations:
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E303",
                    (
                        "ArchiMate/use-case diagram must include "
                        "_archimate-stereotypes.puml or use inline ArchiMate element declarations"
                    ),
                    loc,
                )
            )

    _check_entity_aliases_declared(content, fm, result, loc)


def _check_entity_aliases_declared(content: str, fm: dict, result: VerificationResult, loc: str) -> None:
    entity_ids = fm.get("entity-ids-used")
    if not isinstance(entity_ids, list):
        return

    declared_aliases = _extract_declared_puml_aliases(content)
    for eid in entity_ids:
        eid_str = str(eid)
        matches = list((result.path.parents[2] / MODEL).rglob(f"{eid_str}.md"))
        if matches:
            try:
                entity_text = matches[0].read_text(encoding="utf-8")
            except OSError:
                entity_text = None
            if entity_text is not None:
                alias = _extract_entity_display_alias(entity_text)
                if alias and _normalize_puml_alias(alias) not in declared_aliases:
                    result.issues.append(
                        Issue(
                            Severity.ERROR,
                            "E309",
                            (
                                f"entity-ids-used references '{eid_str}' with display alias '{alias}', "
                                "but that alias is not declared in the PUML body"
                            ),
                            loc,
                        )
                    )


def _extract_declared_puml_aliases(content: str) -> set[str]:
    return _extract_declared_puml_aliases_shared(content)


def check_diagram_artifact_type(fm: dict, result: VerificationResult, loc: str) -> None:
    check_artifact_type(fm, DIAGRAM_ARTIFACT_TYPES, "diagram artifact type", result, loc)


_WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[/\\]")


def _is_absolute_markdown_link(href: str) -> bool:
    return href.startswith(("/", "file://")) or bool(_WINDOWS_ABS_PATH_RE.match(href))


def check_internal_links(content: str, path: Path, result: VerificationResult, loc: str) -> None:
    """W156 (an internal link must be relative) and W155 (it must resolve to something).

    Shared rather than document-only, because prose carrying links is not a property of documents:
    a matrix diagram's body is a markdown table of links, and the rule that finds a link pointing
    at nothing had never been asked about one. A link that no longer resolves is the same fact
    wherever it is written, so it keeps one code rather than gaining a second for a second file
    type.

    The link reading is `references_from`, which is the one reading of what a document's prose
    refers to. This rule used to carry its own regex, making three.
    """
    from src.application.document_links import references_from, strip_anchor  # noqa: PLC0415

    for reference in references_from(content, directory=path.parent):
        file_href = strip_anchor(reference.href)
        if not file_href.endswith(".md"):
            continue
        if _is_absolute_markdown_link(file_href):
            result.issues.append(Issue(
                Severity.WARNING, "W156",
                f"Absolute internal link must be relative: '{file_href}'", loc,
            ))
            continue
        if not reference.target.exists():
            result.issues.append(Issue(
                Severity.WARNING, "W155", f"Unresolvable internal link: '{file_href}'", loc,
            ))


def check_matrix_markdown_shape(fm: dict, content: str, result: VerificationResult, loc: str) -> None:
    """W321 (should declare diagram-type: matrix) and W322 (no table markup found)."""
    if "diagram-type" in fm and str(fm.get("diagram-type")) != "matrix":
        result.issues.append(Issue(
            Severity.WARNING, "W321",
            "Markdown diagram file under diagram-catalog/diagrams should use diagram-type: matrix", loc,
        ))
    if "|" not in content:
        result.issues.append(Issue(
            Severity.WARNING, "W322",
            "Matrix diagram markdown has no table markup; expected at least one matrix table", loc,
        ))
