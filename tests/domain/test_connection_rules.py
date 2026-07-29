"""ArchiMate 4.0 connection-rule conformance.

Sentinel cases transcribed from the ArchiMate 4.0 specification's connection-rule
matrix — Appendix B.5 (direct relationships) and B.6 (grouping/junction). These
pin the loaded ontology to the normative matrix: every PERMITTED triple must be
allowed and every PROHIBITED triple must be absent. The knowledge is embedded
inline here on purpose (no external fixture file): the normative source is the
specification's matrix, and these tests are its executable transcription.

Key rules exercised:
  - internal behaviour (function / process) --realization--> service is PERMITTED
  - service --serving--> / --association-- application-component is PERMITTED
  - active technology (system-software / technology-node / device)
    --serving--> application-component is PERMITTED
  - application-component <-> service realization is PROHIBITED in both directions
    (a component does not realize a service; behaviour does)
"""

from __future__ import annotations

from functools import lru_cache

import pytest

from src.domain.modules.catalogs import ConnectionSemanticsImpl
from src.infrastructure.app_bootstrap import build_module_registry


@lru_cache(maxsize=1)
def _connections() -> ConnectionSemanticsImpl:
    return ConnectionSemanticsImpl(build_module_registry())


def permissible_connection_types(source: str, target: str) -> list[str]:
    return _connections().permissible_connection_types(source, target)

# (source, target, connection) triples the normative matrix marks PERMITTED.
_PERMITTED: list[tuple[str, str, str]] = [
    ("function", "service", "archimate-realization"),
    ("process", "service", "archimate-realization"),
    ("service", "application-component", "archimate-serving"),
    ("service", "application-component", "archimate-association"),
    ("application-component", "service", "archimate-association"),  # association is symmetric
    ("system-software", "application-component", "archimate-serving"),
    ("technology-node", "application-component", "archimate-serving"),
    ("device", "application-component", "archimate-serving"),
]

# (source, target, connection) triples the normative matrix marks PROHIBITED.
_PROHIBITED: list[tuple[str, str, str]] = [
    ("application-component", "service", "archimate-realization"),
    ("service", "application-component", "archimate-realization"),
]


@pytest.mark.parametrize(("source", "target", "connection"), _PERMITTED)
def test_permitted_rule_present(source: str, target: str, connection: str) -> None:
    allowed = permissible_connection_types(source, target)
    assert connection in allowed, (
        f"{source} → {target} [{connection}] must be permitted; allowed={sorted(allowed)}"
    )


@pytest.mark.parametrize(("source", "target", "connection"), _PROHIBITED)
def test_prohibited_rule_absent(source: str, target: str, connection: str) -> None:
    allowed = permissible_connection_types(source, target)
    assert connection not in allowed, (
        f"{source} → {target} [{connection}] must be prohibited; allowed={sorted(allowed)}"
    )
