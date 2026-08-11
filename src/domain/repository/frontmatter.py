"""What counts as the YAML frontmatter block a repository file opens with.

The repository is markdown-with-frontmatter (ADR@1780761609), so this delimitation is a fact about the
stored format — and it was decided **fourteen times**, in five families that do not agree:

| Reading | Sites | Behaviour |
| --- | --- | --- |
| `^---\\n(.*?\\n)---\\n` | 4 | closing fence must be followed by a newline |
| `^---\\n(.*?)^---\\n` (MULTILINE) | 1 | closing fence anywhere at a line start |
| `^---\\n(.*?)\\n---\\s*\\n?` | 1 | tolerates trailing whitespace; final newline optional |
| `startswith("---")` + `find("\\n---", 3)` | 2 | matches `\\n----` too, and needs no newline after the opening fence |
| `\\A---[ \\t]*\\r?\\n.*?\\r?\\n---[ \\t]*(?:\\r?\\n|$)` | 1 | CRLF, trailing whitespace, may end at EOF |

The last of those — `rendering/puml_safety`'s — is a superset of the other four, and is what this module
adopts. Nothing was invented for it: the most careful reading already in the codebase becomes the only
one. The two loosest were the *verifier* and the document write path, so a file could be verified under
one delimitation and rewritten under another.

Measured before unifying: across 975 files in both repositories, the five readings disagree on **zero**.
So this changes no stored content — it removes the possibility of the next edge case being read two ways.

Three answers rather than two, because the verifier legitimately reports "no opening fence" (E011) and
"opening fence with no closing fence" (E012) as different mistakes. Collapsing them into `None` would
have cost a diagnostic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.domain.yaml_documents import parse_yaml

#: Trailing spaces and tabs are tolerated on both fences, `\r\n` as well as `\n` is a line ending, and
#: the closing fence may end the file. Non-greedy body, so the *first* closing fence wins.
#:
#: The content group is **optional**, which is what admits `---\n---\n`: an empty block, written by a
#: diagram that has frontmatter keys pending. Requiring a line ending before the closing fence read that
#: as an unterminated block and lost the file's frontmatter entirely.
_BLOCK = re.compile(r"\A---[ \t]*\r?\n(?:(?P<text>.*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.DOTALL)

#: The opening fence alone, so "malformed opening" and "never closed" stay distinguishable.
_OPENING = re.compile(r"\A---[ \t]*\r?\n")


class FrontmatterProblem(Enum):
    """Why a file has no readable frontmatter block. Distinct because the verifier reports them apart."""

    NO_OPENING_FENCE = "no-opening-fence"
    NO_CLOSING_FENCE = "no-closing-fence"


@dataclass(frozen=True, slots=True)
class Frontmatter:
    """A file's frontmatter block and the document around it."""

    #: The YAML between the fences, fences excluded and no trailing line ending.
    text: str
    #: Everything after the closing fence. Empty when the block ends the file.
    body: str
    #: Index just past the closing fence — where `body` begins in the source.
    end: int


#: Either the block, or why there is none. Exhaustively matchable.
FrontmatterReading = Frontmatter | FrontmatterProblem


def read_frontmatter(source: str) -> FrontmatterReading:
    """The frontmatter block `source` opens with, or which fence is missing."""
    if (match := _BLOCK.match(source)) is not None:
        # `text` is None when the block is empty — the optional group above never participated.
        return Frontmatter(text=match.group("text") or "", body=source[match.end() :], end=match.end())
    if _OPENING.match(source) is None:
        return FrontmatterProblem.NO_OPENING_FENCE
    return FrontmatterProblem.NO_CLOSING_FENCE


def opens_with_frontmatter(source: str) -> bool:
    """Whether `source` begins with a frontmatter fence, whether or not it is ever closed.

    The cheap "is this an artifact file at all" guard several upgrade steps run before doing real work.
    They each spelled it `source.startswith("---")`, which also accepts `----` and `---anything`; this
    requires the fence to be a fence — `---` alone on its line.
    """
    return _OPENING.match(source) is not None


def parse_frontmatter(source: str) -> dict[str, object]:
    """The frontmatter as a mapping — empty when there is none, or when it is not a mapping.

    What most callers want, and the reason they each used to hold a regex. A block that parses to a
    scalar or a list is not frontmatter for any caller here, so it answers the same as no block at all;
    a caller that needs to tell those apart reads `read_frontmatter` and parses the text itself.
    """
    match read_frontmatter(source):
        case Frontmatter(text=text):
            parsed = parse_yaml(text)
            return parsed if isinstance(parsed, dict) else {}
        case _:
            return {}


def body_after_frontmatter(source: str) -> str:
    """`source` with a leading frontmatter block removed, or unchanged when it has none."""
    match read_frontmatter(source):
        case Frontmatter(body=body):
            return body
        case _:
            return source


def replace_frontmatter_text(source: str, text: str) -> str:
    """`source` with its frontmatter YAML replaced by `text`, or unchanged when it has no block.

    The operation the upgrade steps want: they rewrite the YAML region and splice the document back
    together, which each of them was doing with its own match offsets.
    """
    match = _BLOCK.match(source)
    if match is None:
        return source
    return source[: match.start("text")] + text + source[match.end("text") :]
