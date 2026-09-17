"""The release version: three integers, ordered, and one reading of the form.

The project writes its version in five files (`test_one_release_version` holds them together) and a
release tag carries it with a leading `v`. Every consumer that has to compare, order or spell one goes
through this module: `parse_release_version` is the reading, `ReleaseVersion.tag` the spelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

#: `MAJOR.MINOR.PATCH`, optionally after a `v`. Nothing else: the project ships no pre-release
#: suffixes, and a reader that accepted them would order them wrongly against the plain form.
_RELEASE_VERSION = re.compile(r"\Av?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\Z")


class NotAReleaseVersion(ValueError):
    """The text is not `MAJOR.MINOR.PATCH`."""


@total_ordering
@dataclass(frozen=True)
class ReleaseVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        """The git tag a release of this version carries."""
        return f"v{self}"

    def _key(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ReleaseVersion):
            return NotImplemented
        return self._key() < other._key()


def parse_release_version(text: str) -> ReleaseVersion:
    """`0.10.1` or `v0.10.1` → the version; anything else refuses by name."""
    match = _RELEASE_VERSION.match(text.strip())
    if match is None:
        raise NotAReleaseVersion(f"{text!r} is not a release version (MAJOR.MINOR.PATCH)")
    return ReleaseVersion(int(match["major"]), int(match["minor"]), int(match["patch"]))
