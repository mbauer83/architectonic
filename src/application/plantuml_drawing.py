"""What asking PlantUML to draw a source answers, and the port the application asks it through.

PlantUML runs in a Java process, which is infrastructure (`infrastructure.rendering.plantuml_runner`
owns it). The syntax check is an application rule that needs a drawing, so it is handed something that
draws — this port — and reads the answer in these terms, never in a process's.

A drawing is not a verdict. PlantUML draws a refused body too, as a picture of its error message, and
says so separately (`Drawn.refusals`); it draws a layout crash as a picture of the stack trace and may say
nothing at all. Deciding what a drawing means is the caller's business, as it was when the caller read an
exit code and an output directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol

#: The picture formats this product asks PlantUML for.
PictureFormat = Literal["svg", "png"]

#: How PlantUML's pipe mode reports a body it refused: `ERROR`, the 0-based line counted from the
#: `@start` line, and the message — three lines on its error stream, before the picture of the error.
_REFUSAL = re.compile(r"^ERROR\r?\n(\d+)\r?\n(.*?)\r?$", re.MULTILINE)


@dataclass(frozen=True)
class Refusal:
    """One thing PlantUML refused in a body: where, counted from the `@start` line (0-based), and why."""

    line_from_start: int
    message: str


@dataclass(frozen=True)
class Drawn:
    """What PlantUML drew for a source — one picture per diagram in it — and what it said meanwhile."""

    pictures: tuple[bytes, ...]
    diagnostics: str = ""

    @property
    def picture(self) -> bytes | None:
        """The one picture, where the source drew exactly one diagram."""
        return self.pictures[0] if len(self.pictures) == 1 else None

    @property
    def refusals(self) -> tuple[Refusal, ...]:
        """What PlantUML refused, in the order it said so. Empty for a body it accepted."""
        return tuple(Refusal(int(line), message.strip()) for line, message in _REFUSAL.findall(self.diagnostics))


class WhyNotDrawn(Enum):
    """Why there is no drawing at all — as distinct from a drawing of an error."""

    NO_PLANTUML = "plantuml.jar not found"
    NO_JAVA = "java could not be started"
    TIMED_OUT = "PlantUML did not finish in time"
    STOPPED = "the PlantUML process stopped while drawing"


@dataclass(frozen=True)
class NotDrawn:
    """No drawing: why, and what is known beyond that."""

    why: WhyNotDrawn
    detail: str = ""

    @property
    def reason(self) -> str:
        return f"{self.why.value}: {self.detail}" if self.detail else self.why.value


Drawing = Drawn | NotDrawn


class SyntaxDrawing(Protocol):
    """Draws a source the way the syntax check reads it: SVG, with nothing but the sandbox settings."""

    def draw_for_check(self, source: str, *, timeout: float) -> Drawing: ...
