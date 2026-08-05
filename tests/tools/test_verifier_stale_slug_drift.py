"""A reference that resolves but names a slug the artifact no longer has is reported.

The connection files had this check (W121); the diagrams did not, and nothing tested either. That is
how `artifact_verify` came to answer **0 warnings** over 16 stale entity references across 6
diagrams: identity is the `PREFIX@epoch.random` stem, so every one of them resolved, and the only
part a reader can read was wrong with nothing to say so.

The rule itself is one function (`current_spelling_of`) with three reasons to stay silent, so it is
tested directly as well as through both verifier entry points.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import (
    canonical_ids_by_stem,
    current_connection_spelling,
    current_spelling_of,
)
from src.infrastructure.artifact_index import shared_artifact_index

_STEM = "REQ@1000000000.AbcDef"
_CURRENT = f"{_STEM}.current-name"
_STALE = f"{_STEM}.what-it-was-called-before"
_ELSEWHERE = "REQ@1000000000.ZzYyXx.another-requirement"


class TestTheRuleItself:
    def test_a_reference_holding_a_former_slug_is_told_its_current_spelling(self) -> None:
        index = canonical_ids_by_stem([_CURRENT])

        assert current_spelling_of(_STALE, index) == _CURRENT

    def test_a_current_reference_has_nothing_to_report(self) -> None:
        assert current_spelling_of(_CURRENT, canonical_ids_by_stem([_CURRENT])) is None

    def test_an_unknown_stem_has_nothing_to_report(self) -> None:
        """Resolution failure is a different diagnostic, raised where resolution is attempted."""
        assert current_spelling_of(_STALE, canonical_ids_by_stem([_ELSEWHERE])) is None

    def test_an_ambiguous_stem_stays_silent(self) -> None:
        """Both tiers may hold the stem; naming one arbitrarily would libel a correct reference."""
        index = canonical_ids_by_stem([_CURRENT, f"{_STEM}.enterprise-copy"])

        assert current_spelling_of(_STALE, index) is None

class TestAConnectionReference:
    """A connection is keyed by its endpoints' *stems* and its type, so the index holds no slugged
    spelling of one. What can go stale is an endpoint's slug, and the entity index knows that.
    Comparing the entry against the connection index instead would call every fully-spelled
    reference in the repository stale — the index form has no slugs at all.
    """

    _CURRENT_ENTRY = f"{_CURRENT}---{_ELSEWHERE}@@archimate-association"

    def test_a_stale_endpoint_slug_makes_the_whole_entry_readable_again(self) -> None:
        stale_entry = f"{_STALE}---{_ELSEWHERE}@@archimate-association"

        rewritten = current_connection_spelling(stale_entry, canonical_ids_by_stem([_CURRENT, _ELSEWHERE]))

        assert rewritten == self._CURRENT_ENTRY

    def test_a_fully_current_entry_has_nothing_to_report(self) -> None:
        index = canonical_ids_by_stem([_CURRENT, _ELSEWHERE])

        assert current_connection_spelling(self._CURRENT_ENTRY, index) is None

    def test_an_entry_whose_endpoints_are_unknown_has_nothing_to_report(self) -> None:
        assert current_connection_spelling(self._CURRENT_ENTRY, canonical_ids_by_stem([])) is None

    def test_a_malformed_entry_is_left_to_the_rule_that_resolves_it(self) -> None:
        assert current_connection_spelling("not-a-connection-id", canonical_ids_by_stem([_CURRENT])) is None


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(artifact_id: str, name: str) -> str:
    random_key = artifact_id.split(".")[1]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-08-05'
---

<!-- §content -->

## {name}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{random_key}
```
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Two requirements and a connection between them, each spelled currently."""
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    requirements = root / "model" / "motivation" / "requirement"
    _write(requirements / f"{_CURRENT}.md", _entity(_CURRENT, "Current Name"))
    _write(requirements / f"{_ELSEWHERE}.md", _entity(_ELSEWHERE, "Another Requirement"))
    _write(
        requirements / f"{_CURRENT}.outgoing.md",
        f"""\
---
source-entity: {_CURRENT}
version: 0.1.0
status: draft
last-updated: '2026-08-05'
---

<!-- §connections -->

### archimate-association → {_ELSEWHERE}
""",
    )
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True, exist_ok=True)
    return root


def _diagram(*, entity_ids: list[str], connection_ids: list[str]) -> str:
    listed_entities = "".join(f"\n- {eid}" for eid in entity_ids)
    listed_connections = "".join(f"\n- {cid}" for cid in connection_ids)
    return f"""\
---
artifact-id: drift-view
artifact-type: diagram
name: "Drift View"
version: 0.1.0
status: draft
diagram-type: archimate-motivation
last-updated: '2026-08-05'
entity-ids-used:{listed_entities}
connection-ids-used:{listed_connections}
---
@startuml drift-view
!include ../_archimate-stereotypes.puml
title Drift View
rectangle "Current Name" <<Requirement>> as REQ_AbcDef
rectangle "Another Requirement" <<Requirement>> as REQ_ZzYyXx
REQ_AbcDef -- REQ_ZzYyXx
@enduml
"""


def _verify_diagram(repo: Path, content: str):  # type: ignore[no-untyped-def]
    path = repo / "diagram-catalog" / "diagrams" / "drift-view.puml"
    _write(path, content)
    registry = ArtifactRegistry(shared_artifact_index(repo))
    verifier = ArtifactVerifier(registry, check_puml_syntax=False, catalogs=_catalogs())
    return verifier.verify_diagram_file(path)


_CURRENT_CONNECTION = f"{_CURRENT}---{_ELSEWHERE}@@archimate-association"
_STALE_CONNECTION = f"{_STALE}---{_ELSEWHERE}@@archimate-association"


class TestADiagramsReferences:
    def test_a_stale_entity_reference_is_reported(self, repo: Path) -> None:
        result = _verify_diagram(
            repo, _diagram(entity_ids=[_STALE, _ELSEWHERE], connection_ids=[_CURRENT_CONNECTION])
        )

        drift = [i for i in result.issues if i.code == "W305"]
        assert len(drift) == 1
        assert _STALE in drift[0].message
        assert _CURRENT in drift[0].message

    def test_a_stale_entity_reference_is_a_warning_and_nothing_more(self, repo: Path) -> None:
        """Resolution is unaffected, so refusing the diagram would be wrong."""
        result = _verify_diagram(
            repo, _diagram(entity_ids=[_STALE, _ELSEWHERE], connection_ids=[_CURRENT_CONNECTION])
        )

        assert result.valid, [i.message for i in result.issues if i.severity == "error"]

    def test_a_stale_connection_reference_is_reported(self, repo: Path) -> None:
        result = _verify_diagram(
            repo, _diagram(entity_ids=[_CURRENT, _ELSEWHERE], connection_ids=[_STALE_CONNECTION])
        )

        drift = [i for i in result.issues if i.code == "W306"]
        assert len(drift) == 1
        assert _STALE_CONNECTION in drift[0].message
        assert _CURRENT_CONNECTION in drift[0].message

    def test_current_references_are_reported_neither_way(self, repo: Path) -> None:
        result = _verify_diagram(
            repo, _diagram(entity_ids=[_CURRENT, _ELSEWHERE], connection_ids=[_CURRENT_CONNECTION])
        )

        assert [i.code for i in result.issues if i.code in {"W305", "W306"}] == []


class TestAConnectionFilesTarget:
    def test_a_stale_target_slug_is_reported(self, repo: Path) -> None:
        """W121, which had no test of its own — the diagram side now reads the same rule."""
        source = "REQ@1000000001.SrcAaa.the-source"
        _write(
            repo / "model" / "motivation" / "requirement" / f"{source}.md",
            _entity(source, "The Source"),
        )
        outgoing = repo / "model" / "motivation" / "requirement" / f"{source}.outgoing.md"
        _write(
            outgoing,
            f"""\
---
source-entity: {source}
version: 0.1.0
status: draft
last-updated: '2026-08-05'
---

<!-- §connections -->

### archimate-association → {_STALE}
""",
        )
        registry = ArtifactRegistry(shared_artifact_index(repo))
        result = ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(outgoing)

        assert [i.code for i in result.issues if i.code == "W121"] == ["W121"]
        assert result.valid, [i.message for i in result.issues if i.severity == "error"]
