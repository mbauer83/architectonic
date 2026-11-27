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

from collections.abc import Iterable, Mapping

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


def content_rank(value: str | None) -> int:
    """How sensitive a piece of content is, for deciding whether a reader may see it.

    Unknown or malformed input ranks as TLP:RED. This is the exposure side of the order, where a
    misspelt level must withhold rather than disclose: reading it as the least sensitive, as two
    copies of this order once did, showed `tlp: "red "` and `tlp: null` content to every reader.
    """
    return TLP_ORDER.index(normalize_tlp(value, default=TLP_RED))


def record_tlp(record: Mapping[str, object]) -> str | None:
    """The level a stored record carries, or None when it carries none.

    None ranks as TLP:RED wherever content is disclosed (`content_rank`, `most_sensitive`). No kind of
    record is given a default level here: a default below RED is a level nobody assigned, and reading
    a record that lost its level as TLP:WHITE disclosed it to every reader.
    """
    value = record.get("tlp")
    return value if isinstance(value, str) else None


def ceiling_rank(value: str | None) -> int:
    """How much a reader may see; an unknown ceiling admits only TLP:WHITE."""
    return TLP_ORDER.index(normalize_tlp(value, default=TLP_WHITE))


def exceeds_ceiling(value: str | None, ceiling: str | None) -> bool:
    """True when content at *value* must be withheld from a reader whose ceiling is *ceiling*."""
    return content_rank(value) > ceiling_rank(ceiling)


def most_sensitive(values: Iterable[str | None]) -> str | None:
    """The classification of something derived from *values*; None when there is nothing to classify.

    An unknown contributor counts as TLP:RED: a derived figure is at least as sensitive as the least
    certain thing it was computed from.
    """
    ranks = [content_rank(value) for value in values]
    return TLP_ORDER[max(ranks)] if ranks else None
