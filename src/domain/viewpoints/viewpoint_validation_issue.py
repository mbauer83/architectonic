"""The structured issue type ``validate_viewpoint_definition`` returns.

Deliberately distinct from the artifact verifier's ``Issue`` (E180/W180/W181/W182): the
verifier judges *artifacts against the model*; this type judges *definitions against the
catalogs* — different lifecycles, different consumers, no shared code space.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ValidationMode = Literal["load", "save", "persist_edit"]
IssueSeverity = Literal["error", "warning"]

VALID_VALIDATION_MODES: frozenset[str] = frozenset({"load", "save", "persist_edit"})


@dataclass(frozen=True)
class ViewpointValidationIssue:
    severity: IssueSeverity
    code: str  # stable kebab-case id, e.g. "unknown-attribute", "depth-cap-exceeded"
    path: str  # JSON-pointer-style path into the definition
    message: str
    expected: str | None = None
    found: str | None = None
