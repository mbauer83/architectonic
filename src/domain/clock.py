"""Central, timezone-safe clock for IDs and timestamps.

Every artifact, entity, assurance node, baseline, and audit entry derives its
epoch and ISO timestamp from this module, so the values are identical regardless
of the host machine's timezone or locale.

Guarantees:
  * ``epoch_seconds()`` returns POSIX seconds (UTC by definition — independent of
    ``TZ``).
  * ``utc_now_iso()`` returns a UTC ISO-8601 instant with a trailing ``Z``.
  * ``utc_now_compact()`` returns a filename-safe UTC stamp (``YYYYMMDDTHHMMSSZ``).

Never use ``time.localtime``, ``datetime.now()`` without a tzinfo, ``mktime`` or
``fromtimestamp`` for persisted values — those depend on the local timezone and
will diverge across deployments. Route all such needs through this module.

Because this module is the single source of "now", it also owns the seam for freezing
it: ``frozen_now()`` pins every reader below to one instant so a caller that needs a
deterministic persisted stamp (a golden file, a migration acceptance check) gets one
without patching internals. Unset by default — production behaviour is unchanged.
"""

from __future__ import annotations

import calendar
import time
from collections.abc import Iterator
from contextlib import contextmanager

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_COMPACT_FORMAT = "%Y%m%dT%H%M%SZ"

_now_override: float | None = None
"""Pinned POSIX instant, or None to read the real clock. Set via set_now_override()."""


def _now() -> float:
    """The current POSIX instant every reader in this module derives from."""
    return time.time() if _now_override is None else _now_override


def epoch_from_iso(stamp: str) -> float:
    """Parse a ``YYYY-MM-DDTHH:MM:SSZ`` UTC stamp into POSIX seconds.

    ``calendar.timegm`` (not ``mktime``) so the result is timezone-independent.
    """
    return float(calendar.timegm(time.strptime(stamp, _ISO_FORMAT)))


def set_now_override(instant: float | str | None) -> None:
    """Pin "now" to *instant* (POSIX seconds or a canonical UTC ISO stamp); None restores
    the real clock."""
    global _now_override
    _now_override = epoch_from_iso(instant) if isinstance(instant, str) else instant


@contextmanager
def frozen_now(instant: float | str) -> Iterator[None]:
    """Pin "now" for the duration of the block, restoring the previous setting after."""
    previous = _now_override
    set_now_override(instant)
    try:
        yield
    finally:
        set_now_override(previous)


def epoch_seconds() -> int:
    """Return the current time as integer POSIX seconds (UTC, timezone-independent)."""
    return int(_now())


def utc_now_iso() -> str:
    """Return the current UTC instant as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return time.strftime(_ISO_FORMAT, time.gmtime(_now()))


def utc_now_compact() -> str:
    """Return the current UTC instant as a filename-safe ``YYYYMMDDTHHMMSSZ`` stamp."""
    return time.strftime(_COMPACT_FORMAT, time.gmtime(_now()))
