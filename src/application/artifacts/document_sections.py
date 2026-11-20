"""A document's body, and the `##` sections it is divided into.

Here rather than beside the verifier's document rules, where these two functions began: the
promotion closure reads sections too, and so does the reading of a document's typed tables — which
the verifier's rules then call, so a reader that had to import the rules for this would import its
own caller.

The heading itself is spelled once, in `src.application.document_links`, which needs it to say which
section a link sits in.
"""

from __future__ import annotations

from src.application.document_links import SECTION_HEADING_RE
from src.domain.repository.frontmatter import body_after_frontmatter


def document_body(content: str) -> str:
    """Document content with the YAML frontmatter block removed."""
    return body_after_frontmatter(content)


def document_section_spans(body: str) -> dict[str, str]:
    """Each section's text, heading included, by its name. Sections sharing a name are joined."""
    matches = list(SECTION_HEADING_RE.finditer(body))
    spans: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        spans.setdefault(name, []).append(body[match.start() : end])
    return {name: "\n".join(parts) for name, parts in spans.items()}
