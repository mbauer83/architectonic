"""A document's body, the `##` sections it is divided into, and the headings beneath them.

Here rather than beside the verifier's document rules, where the first two functions began: the
promotion closure reads sections too, and so does the reading of a document's typed tables — which
the verifier's rules then call, so a reader that had to import the rules for this would import its
own caller.

The heading itself is spelled once, in `src.application.document_links`, which needs it to say which
section a link sits in.

**A heading's path** is the titles from its `##` section down to itself — `("Decision",)`, or
`("Decision", "Consequences")` for a `###` beneath it. A heading's part of the body runs to the next
heading at its own level or above, so it holds the headings beneath it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.document_links import HEADING_RE
from src.domain.repository.frontmatter import body_after_frontmatter

_SECTION_LEVEL = 2


@dataclass(frozen=True)
class HeadingSpan:
    """One heading and the part of the body it opens, as offsets into that body."""

    path: tuple[str, ...]
    level: int
    #: Where the heading line begins.
    start: int
    #: Where the text under the heading begins: the line after it, or the end of the body.
    content_start: int
    #: Where the next heading at this level or above begins, or the end of the body.
    end: int

    @property
    def name(self) -> str:
        return self.path[-1]


def document_body(content: str) -> str:
    """Document content with the YAML frontmatter block removed."""
    return body_after_frontmatter(content)


def document_headings(body: str) -> tuple[HeadingSpan, ...]:
    """Every heading of `body` from the section level down, in order, each with its path."""
    found = [
        (len(match.group(1)), match.group(2).strip(), match.start(), match.end())
        for match in HEADING_RE.finditer(body)
    ]
    spans: list[HeadingSpan] = []
    above: list[tuple[int, str]] = []
    for index, (level, title, start, line_end) in enumerate(found):
        above = [*((held, name) for held, name in above if held < level), (level, title)]
        spans.append(
            HeadingSpan(
                path=tuple(name for _, name in above),
                level=level,
                start=start,
                content_start=min(line_end + 1, len(body)),
                end=next((later[2] for later in found[index + 1 :] if later[0] <= level), len(body)),
            )
        )
    return tuple(spans)


def document_sections(body: str) -> tuple[HeadingSpan, ...]:
    """The `##` sections of `body`, in order."""
    return tuple(heading for heading in document_headings(body) if heading.level == _SECTION_LEVEL)


def document_section_spans(body: str) -> dict[str, str]:
    """Each section's text, heading included, by its name. Sections sharing a name are joined."""
    spans: dict[str, list[str]] = {}
    for section in document_sections(body):
        spans.setdefault(section.name, []).append(body[section.start : section.end])
    return {name: "\n".join(parts) for name, parts in spans.items()}
