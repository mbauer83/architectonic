"""What an element looks like, as the ontology that owns the vocabulary declares it.

Two visual properties carry meaning and were previously carried by nobody: the **colour** that says
which domain an element belongs to, and the **corner shape** that says what kind of thing it is.
Both were hardcoded — the colour three times, in a PUML generator and twice in the frontend, with
values that disagreed on every domain and one palette missing `implementation` entirely, so the
same element was one colour in a diagram and another in the graph explorer. The corner shape was
expressed nowhere at all.

**Structural, not pictorial — the same rule `relation_notation` follows.** A corner style says
`diagonal`, never `motivation`, so a renderer honours it without knowing this ontology's
vocabulary and a second modelling language can declare its own categories in the same terms.

**Keyed on classes, not on types.** Entity types already declare the classes they belong to and the
ontology already declares what those classes are, so a corner style names classes and resolves
through them. That is the shape `behavioral_element_classes` established: short lists that read as
one statement of intent, rather than a property repeated on forty types where an auditor has to
re-collect the set mentally to see what it says.

**De-emphasis is derived, and derived once.** A surface that needs a muted variant mixes toward a
declared base by a declared amount rather than carrying a second palette — which is how the first
three came about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

#: How an element's corners are drawn. A closed set: a renderer must be able to exhaust it.
CornerStyle = Literal["square", "rounded", "diagonal"]

CORNER_STYLES: Final[tuple[CornerStyle, ...]] = ("square", "rounded", "diagonal")

#: What an element looks like when its ontology declares nothing about it. Square corners and no
#: colour: the least specific thing that is still a drawable element.
DEFAULT_CORNER: Final[CornerStyle] = "square"


@dataclass(frozen=True)
class ColorMix:
    """A colour derived from a declared one by mixing toward another.

    One shape for every derived colour this ontology needs — a muted variant, a border, a container
    tint. Declared rather than left to each surface, because "add some white" is exactly the kind
    of instruction that becomes four slightly different greys, which is how three palettes that
    agreed on nothing came about. `amount` is the fraction of `toward` mixed in, so 0 is the colour
    untouched and 1 is `toward` itself.
    """

    toward: str = "#FFFFFF"
    amount: float = 0.0

    @property
    def is_declared(self) -> bool:
        return self.amount > 0


@dataclass(frozen=True)
class ElementAppearance:
    """One ontology's statement of how its elements are drawn.

    Every field defaults to empty, and an empty declaration resolves to no colour and square
    corners. That is the honest answer for an ontology that has not said: silence is the absence
    of the declaration, not a claim that every element is square and grey.
    """

    domain_colors: Mapping[str, str] = field(default_factory=dict)
    corner_classes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    de_emphasis: ColorMix = ColorMix()
    border: ColorMix = ColorMix()

    @property
    def is_empty(self) -> bool:
        return not (self.domain_colors or self.corner_classes)

    def color_for(self, domain: str) -> str | None:
        """The colour this ontology gives that domain, or None where it declares none."""
        return self.domain_colors.get(domain)

    def corner_for(self, classes: Sequence[str]) -> CornerStyle:
        """The corner style for an element carrying these classes.

        Resolved in the declared order of `CORNER_STYLES`, so a type carrying classes from two
        categories gets a stable answer rather than one that depends on mapping iteration. A type
        matching none takes the default, which is what an unclassified element already looks like.
        """
        carried = frozenset(str(name) for name in classes)
        for style in CORNER_STYLES:
            if carried & self.corner_classes.get(style, frozenset()):
                return style
        return DEFAULT_CORNER

    def de_emphasized(self, color: str) -> str:
        """*color*, muted by the declared rule. Returned unchanged where no rule is declared."""
        return self._mixed(color, self.de_emphasis)

    def border_for(self, color: str) -> str:
        """The line drawn around an element filled with *color*.

        Derived rather than declared per domain, so a palette cannot half-move: every earlier
        table carried a fill and a border side by side, and nothing held them to each other.
        """
        return self._mixed(color, self.border)

    @staticmethod
    def _mixed(color: str, rule: ColorMix) -> str:
        return _mix(color, rule.toward, rule.amount) if rule.is_declared else color

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "ElementAppearance":
        """Read the declaration from an ontology's parsed YAML. Absent keys mean empty."""
        raw = data.get("element_appearance")
        if not isinstance(raw, Mapping):
            return cls()
        colors = raw.get("domain_colors")
        corners = raw.get("corner_classes")
        muted = raw.get("de_emphasis")
        return cls(
            domain_colors={
                str(domain): str(value) for domain, value in colors.items()
            } if isinstance(colors, Mapping) else {},
            corner_classes={
                str(style): frozenset(str(name) for name in names)
                for style, names in corners.items()
                if style in CORNER_STYLES and isinstance(names, (list, tuple))
            } if isinstance(corners, Mapping) else {},
            de_emphasis=_mix_rule(muted, default_toward="#FFFFFF"),
            border=_mix_rule(raw.get("border"), default_toward="#000000"),
        )


def _mix_rule(raw: object, *, default_toward: str) -> ColorMix:
    if not isinstance(raw, Mapping):
        return ColorMix(toward=default_toward)
    try:
        amount = float(str(raw.get("amount", 0)))
    except ValueError:
        return ColorMix(toward=default_toward)
    return ColorMix(
        toward=str(raw.get("toward") or default_toward), amount=max(0.0, min(1.0, amount))
    )


def _channels(color: str) -> tuple[int, int, int] | None:
    value = color.lstrip("#")
    if len(value) != 6:
        return None
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return None


def _mix(color: str, toward: str, amount: float) -> str:
    """*color* moved *amount* of the way to *toward*. Either colour unreadable leaves it alone."""
    left, right = _channels(color), _channels(toward)
    if left is None or right is None:
        return color
    mixed = (round(a + (b - a) * amount) for a, b in zip(left, right, strict=True))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)
