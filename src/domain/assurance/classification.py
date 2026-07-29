"""Traffic Light Protocol (TLP) classification ordering and the publishability boundary.

TLP is a total order of disclosure sensitivity:

    TLP:WHITE  <  TLP:GREEN  <  TLP:AMBER  <  TLP:RED

This module is the single source of truth for that order and for the *publishability*
boundary that separates content safe to persist in a shared (e.g. git-tracked) location from
content that must stay confidential. Assurance diagram confidentiality keys off this boundary:
publishable diagrams may render and persist their source to the catalog; confidential ones
must be gated/redirected. Keeping the rule here — rather than as an ad-hoc per-feature flag —
means one definition governs every confidentiality decision.
"""

from __future__ import annotations

TLP_WHITE = "TLP:WHITE"
TLP_GREEN = "TLP:GREEN"
TLP_AMBER = "TLP:AMBER"
TLP_RED = "TLP:RED"

# Ascending sensitivity. Index = rank.
TLP_ORDER: tuple[str, ...] = (TLP_WHITE, TLP_GREEN, TLP_AMBER, TLP_RED)

# Content at or below this level is safe to share (render to disk, persist source to the
# git-tracked catalog). Above it, content is confidential and must be gated/redirected.
PUBLISHABLE_CEILING = TLP_GREEN


def normalize_tlp(value: str | None, *, default: str = TLP_AMBER) -> str:
    """Return a canonical TLP level, falling back to *default* for unknown/blank input.

    The default is deliberately conservative (TLP:AMBER, confidential): unclassified or
    malformed assurance content is treated as sensitive until explicitly marked otherwise.
    """
    if not isinstance(value, str):
        return default
    candidate = value.strip().upper()
    return candidate if candidate in TLP_ORDER else default


def tlp_rank(value: str | None) -> int:
    """Sensitivity rank (0 = WHITE … 3 = RED); unknown input ranks as the conservative default."""
    return TLP_ORDER.index(normalize_tlp(value))


def is_publishable(value: str | None) -> bool:
    """True if content at this classification may be shared (rendered + persisted publicly)."""
    return tlp_rank(value) <= TLP_ORDER.index(PUBLISHABLE_CEILING)
