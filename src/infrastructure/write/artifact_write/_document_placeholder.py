"""Document placeholder-body generation for ``document.create_document``.

Split out of ``document.py`` to keep its CRUD/write-path functions the
cohesive unit; these are pure functions over a doc-type schema's sections.
"""


def _validate_section_templates(
    section_templates: object,
    required_sections: list[str],
    doc_type: str,
) -> None:
    if not isinstance(section_templates, dict):
        raise ValueError(
            f"Doc-type {doc_type!r}: section_templates must be an object, "
            f"got {type(section_templates).__name__}"
        )
    valid_sections = set(required_sections)
    for key, value in section_templates.items():
        if key not in valid_sections:
            raise ValueError(
                f"Doc-type {doc_type!r}: section_templates key {key!r} is not in "
                f"required_sections {required_sections}"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"Doc-type {doc_type!r}: section_templates[{key!r}] must be a string, "
                f"got {type(value).__name__}"
            )


def _build_placeholder_body(
    required_sections: list[object],
    section_templates: dict[str, str] | None = None,
) -> str:
    parts = []
    templates = section_templates or {}
    for section in required_sections:
        if isinstance(section, dict):
            section_name = str(section.get("name") or "").strip()
            template_value = section.get("template")
            template_body = str(template_value) if template_value is not None else None
            hint = _section_expected_link_hint(section)
        else:
            section_name = str(section)
            template_body = templates.get(section_name)
            hint = ""
        if not section_name:
            continue
        intro = f"## {section_name}\n\n{hint}"
        if template_body is not None:
            parts.append(f"{intro}{template_body.rstrip()}\n")
        else:
            parts.append(f"{intro}<!-- Add content here -->\n")
    return "\n".join(parts)


def _section_expected_link_hint(section: dict) -> str:
    required = _string_list(section.get("required_entity_type_connections"))
    suggested = _string_list(section.get("suggested_entity_type_connections"))
    parts = []
    if required:
        parts.append(f"required: {', '.join(required)}")
    if suggested:
        parts.append(f"suggested: {', '.join(suggested)}")
    if not parts:
        return ""
    return f"<!-- Expected entity links for this section: {'; '.join(parts)} -->\n"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
