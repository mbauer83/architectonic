"""What a value has to survive to sit on a PUML line at all.

Two escapes, and both are about the line rather than about any notation on it: a backslash is
PlantUML's own escape character, so an unescaped one eats the character after it, and a newline ends
the line, so a multi-line value silently becomes body text the parser then misreads.

Here because three renderers needed it and two of them had grown byte-identical copies. What is
*not* here is any delimiter a particular notation reserves — a swimlane header is bounded by `|` and
an activity label must therefore replace it, which is the activity module's rule and belongs with the
activity module. That distinction is why one shared function was the wrong shape: the shared part is
the line, and the reserved characters are each notation's own.
"""

from __future__ import annotations


def puml_line_text(value: str) -> str:
    """*value*, safe to place on a PUML line: backslashes escaped, newlines flattened to spaces."""
    return value.replace("\\", "\\\\").replace("\n", " ")
