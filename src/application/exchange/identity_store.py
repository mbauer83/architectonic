"""Exchange identifier <-> artifact ID identity mapping (D10, parent plan §4.5, WU-F3a).

A sidecar map, not a frontmatter extra: ``edit_entity`` re-derives an entity's frontmatter
from its own known fields on every edit and does not round-trip arbitrary unknown
frontmatter keys, so a custom ``exchange_id:`` field would be silently dropped on the
entity's first post-import edit. A repo-local sidecar avoids depending on that machinery.
"""

from __future__ import annotations

from typing import Protocol


class ExchangeIdentityStore(Protocol):
    def artifact_id_for(self, exchange_id: str) -> str | None: ...

    def record(self, exchange_id: str, artifact_id: str) -> None: ...
