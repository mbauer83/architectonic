"""The architecture graph actually reaches the failure-mode surfaces.

Every function in this feature that reads the architecture graph takes it as a parameter with an
empty default, so that a caller without a model still gets an answer. That default is also how the
whole structural half of the method came to be implemented, unit-tested, and reachable from nothing:
each test called the function directly and passed, while no production caller ever supplied a graph.
The load-bearing half of the candidate set was always empty, no rationale ever cited a
classification, and the occurrence basis was a digest of the empty list — so no security snapshot
moving could ever retire a judgement.

These tests are therefore about the wiring, not the functions. The source scans below fail if a read
path stops feeding the graph, and the behavioural tests fail if the graph stops changing the answer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.assurance.fmea_architecture import (
    ArchitectureBasis,
    read_architecture_basis,
)
from src.application.assurance.fmea_occurrence_evidence import ElementSecurityBasis
from src.application.assurance.fmea_rows import candidates, matrix_rows
from src.application.verification.assurance_verifier import verify_store
from src.domain.artifact_id import canonical_entity_key
from src.domain.assurance.failure_modes import FAILURE_GUIDEWORD_SLUGS

SRC = Path(__file__).resolve().parents[2] / "src"

#: The one call that is deliberately given no graph, with the reason recorded at the call site: it
#: reports on the single node just written, and element-scoped findings would bury that answer.
GRAPH_FREE_VERIFY_CALLS = {"src/application/assurance/mutations.py"}

# Written in the slugged form a GUI navigation carries, and looked up in the stable form the
# graph keys on — the two spellings meeting is part of what the wiring has to get right.
PROVIDER = "APP@1000000000.prov.shared-provider"
DEPENDENT = "APP@1000000001.dep.only-dependent"
ELEMENT = "APP@1000000002.elem.analysed-element"
DATA = "DOB@1000000003.data.customer-records"
PROVIDER_KEY = canonical_entity_key(PROVIDER)
ELEMENT_KEY = canonical_entity_key(ELEMENT)
DATA_KEY = canonical_entity_key(DATA)

#: Any of the five would do; a failure mode with no guideword occupies no cell, so a staged row
#: has to name one.
GUIDEWORD = FAILURE_GUIDEWORD_SLUGS[0]


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


@dataclass(frozen=True)
class _Connection:
    artifact_id: str
    source: str
    target: str
    conn_type: str


@dataclass(frozen=True)
class _Entity:
    """The fields of `EntityRecord` the basis reads.

    `name` and `display_label` are here because the basis carries them: a matrix row has to be able
    to name its element, and a stub missing them under-implements the record the port declares.
    """

    artifact_id: str
    artifact_type: str
    attributes: dict[str, object]
    name: str = ""
    display_label: str = ""


class _Model:
    """The two reads `ArchitectureModelSource` asks for, and nothing else."""

    def __init__(self, connections: list[_Connection], entities: list[_Entity]) -> None:
        self._connections = connections
        self._entities = entities

    def list_connections(self) -> list[Any]:
        return list(self._connections)

    def list_entities(self) -> list[Any]:
        return list(self._entities)


class _Catalog:
    def __init__(self, types: dict[str, _TypeInfo]) -> None:
        self._types = types

    def all_connection_types(self) -> dict[str, _TypeInfo]:
        return dict(self._types)


def _basis() -> ArchitectureBasis:
    """A graph in which one provider carries enough typed dependents to be worth reporting.

    Four of them, because `MANY_DEPENDENTS` is the threshold and the sole-provider reason no longer
    exists: it claimed "nothing can stand in for it", which the model never states — see
    `load_bearing_but_unanalysed`. A single dependent is now correctly silent.
    """
    return read_architecture_basis(
        _Model(
            [
                _Connection("C1", DEPENDENT, PROVIDER, "archimate-serving"),
                # Distinct epoch+random parts, not distinct slugs: `canonical_entity_key` keeps
                # only `PREFIX@epoch.random`, so four ids differing in the slug alone would
                # canonicalise to one dependent and the count would stay at 1.
                _Connection("C1b", "APP@1000000004.depb.second-dependent", PROVIDER, "archimate-serving"),
                _Connection("C1c", "APP@1000000005.depc.third-dependent", PROVIDER, "archimate-serving"),
                _Connection("C1d", "APP@1000000006.depd.fourth-dependent", PROVIDER, "archimate-serving"),
                _Connection("C2", ELEMENT, DATA, "archimate-access"),
            ],
            [_Entity(DATA, "data-object", {"Sensitivity": "Confidential"},
                     name="Evidence Store", display_label="Evidence Store")],
        ),
        connection_types=_Catalog({
            "archimate-serving": _TypeInfo("dependency", 4),
            "archimate-access": _TypeInfo(None, None),
        }),
    )


def _calls_named(name: str) -> list[tuple[str, ast.Call]]:
    """Every call to `name` in production source, with the file it appears in."""
    found: list[tuple[str, ast.Call]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            called = getattr(node, "func", None)
            if isinstance(node, ast.Call) and isinstance(called, ast.Name) and called.id == name:
                found.append((str(path.relative_to(SRC.parent)), node))
    return found


class TestEveryReadPathIsFedTheGraph:
    """A source scan, because a behavioural test cannot see a caller that was never written."""

    def test_the_matrix_builder_is_never_called_without_a_graph(self) -> None:
        calls = _calls_named("matrix_rows")
        assert calls, "matrix_rows has no production caller at all"

        starved = [
            path for path, call in calls
            if "basis" not in {kw.arg for kw in call.keywords if kw.arg}
        ]

        assert starved == [], (
            "these read paths build the matrix without the architecture graph, so the load-bearing "
            f"half of the candidate set is empty wherever they are used: {starved}"
        )

    def test_the_verifier_is_given_the_graph_wherever_a_reader_sees_the_result(self) -> None:
        starved = {
            path for path, call in _calls_named("verify_store")
            if "basis" not in {kw.arg for kw in call.keywords if kw.arg}
        }

        assert starved <= GRAPH_FREE_VERIFY_CALLS, (
            "these callers verify without the architecture graph, so the findings comparing the two "
            f"models are silently skipped: {sorted(starved - GRAPH_FREE_VERIFY_CALLS)}"
        )


class TestTheGraphDoesNotProduceRows:
    """The structural signal is reported, never queued as work.

    Nominating load-bearing elements was measured on the repository this software describes: it
    produced 107 rows beside the 3 the analysis had reached. No threshold rescued it — the same model
    yields 72, 31 or 23 on numbers with no principled defence — so the claim is made as a finding and
    acting on it means adding the element deliberately.
    """

    def test_a_load_bearing_element_gets_no_row_however_much_relies_on_it(self) -> None:
        assert candidates(nodes=[], arch_refs=[]) == ()
        assert matrix_rows(nodes=[], edges=[], arch_refs=[], assessments={}, basis=_basis()) == []

    def test_a_row_carries_the_name_and_type_of_the_element_it_asks_about(self) -> None:
        """A row keyed by a bare artifact id gives an analyst no idea which element they are being
        asked to assess, and a hundred of them read as noise. Both labels come from the basis, which
        is the one place these surfaces obtain the architecture graph."""
        rows = matrix_rows(
            nodes=[{"node_id": "CSN@1", "node_type": "control-structure-node"}],
            edges=[],
            arch_refs=[{
                "assurance_node_id": "CSN@1", "arch_artifact_id": DATA, "ref_type": "binds-to",
            }],
            assessments={},
            basis=_basis(),
        )

        assert [row["element_name"] for row in rows] == ["Evidence Store"]
        assert [row["element_type"] for row in rows] == ["data-object"]

    def test_a_row_for_an_element_the_model_cannot_describe_still_exists(self) -> None:
        """The empty label is honest: the element is bound and worth asking about, and inventing a
        name for one nothing can describe would be worse than showing its id."""
        rows = matrix_rows(
            nodes=[{"node_id": "CSN@1", "node_type": "control-structure-node"}],
            edges=[],
            arch_refs=[{
                "assurance_node_id": "CSN@1", "arch_artifact_id": ELEMENT, "ref_type": "binds-to",
            }],
            assessments={},
            basis=_basis(),
        )

        assert [row["element_id"] for row in rows] == [ELEMENT_KEY]
        assert rows[0]["element_name"] == ""
        assert rows[0]["element_type"] == ""

    def test_the_analysis_is_the_only_nominator(self) -> None:
        offered = candidates(
            nodes=[{"node_id": "CSN@1", "node_type": "control-structure-node"}],
            arch_refs=[{
                "assurance_node_id": "CSN@1", "arch_artifact_id": ELEMENT, "ref_type": "binds-to",
            }],
        )

        assert [c.element_id for c in offered] == [ELEMENT_KEY]
        assert offered[0].nominated_by == ("control-structure",)

    def test_a_cell_cites_the_classification_of_data_its_element_reaches(self, unlocked_store: Any) -> None:
        """The point of not adding a second classification attribute: it is read through the graph."""
        node_id = str(unlocked_store.create_node(
            "failure-mode", "Records are served to the wrong caller", failure_type=GUIDEWORD,
        ))
        unlocked_store.register_arch_ref(node_id, ELEMENT, "binds-to")
        controller = str(unlocked_store.create_node("control-structure-node", "Element"))
        unlocked_store.register_arch_ref(controller, ELEMENT, "binds-to")

        rows = matrix_rows(
            nodes=unlocked_store.list_nodes(), edges=unlocked_store.list_edges(),
            arch_refs=unlocked_store.list_arch_refs(), assessments={}, basis=_basis(),
        )
        row = next(r for r in rows if r["element_id"] == ELEMENT_KEY)
        drafts = [str(cell["occurrence_rationale_draft"]) for cell in row["cells"]]

        assert any(f"accesses {DATA_KEY}, classified Confidential" in draft for draft in drafts)


def _record_occurrence(unlocked_store: Any, node_id: str, digest: str) -> None:
    unlocked_store.write_fmea_assessment(
        node_id=node_id, factor="occurrence", basis_digest=digest,
        value="occasional", justification="Judged against the picture at the time.",
        author="tester",
    )


def _occurrence_digest(unlocked_store: Any, node_id: str, *, security: dict[str, ElementSecurityBasis]) -> str:
    result = verify_store(unlocked_store, basis=_basis(), security=security)
    del result  # the digest is read from the derivation, not the findings
    from src.application.assurance.fmea_rows import matrix_rows as build

    rows = build(
        nodes=unlocked_store.list_nodes(), edges=unlocked_store.list_edges(), arch_refs=unlocked_store.list_arch_refs(),
        assessments={}, basis=_basis(),
        security=security,
    )
    row = next(r for r in rows if r["element_id"] == ELEMENT_KEY)
    cell = next(c for c in row["cells"] if c["node_id"] == node_id)
    return str(dict(dict(cell["factors"])["occurrence"])["basis_digest"])


class TestASecuritySnapshotMovingRetiresOnlySecurityJudgements:
    """W513 is what makes a disclosure change the analysis instead of silently invalidating it."""

    def _staged(self, unlocked_store: Any, concern_class: str) -> str:
        controller = str(unlocked_store.create_node("control-structure-node", "Element"))
        unlocked_store.register_arch_ref(controller, ELEMENT, "binds-to")
        node_id = str(unlocked_store.create_node(
            "failure-mode", f"A {concern_class} failure of the element",
            concern_class=concern_class, failure_type=GUIDEWORD,
        ))
        unlocked_store.register_arch_ref(node_id, ELEMENT, "binds-to")
        return node_id

    def test_a_new_snapshot_flags_a_prior_security_concern_judgement_stale(self, unlocked_store: Any) -> None:
        node_id = self._staged(unlocked_store, "security")
        before = {ELEMENT_KEY: ElementSecurityBasis(vulnerability_ids=("CVE-2026-1",), snapshot_id="SNP@1")}
        _record_occurrence(unlocked_store, node_id, _occurrence_digest(unlocked_store, node_id, security=before))

        after = {ELEMENT_KEY: ElementSecurityBasis(vulnerability_ids=("CVE-2026-1", "CVE-2026-2"), snapshot_id="SNP@2")}
        codes = [i.code for i in verify_store(unlocked_store, basis=_basis(), security=after).issues
                 if i.node_id == node_id]

        assert "W513" in codes

    def test_the_same_judgement_stands_while_the_snapshot_has_not_moved(self, unlocked_store: Any) -> None:
        node_id = self._staged(unlocked_store, "security")
        unchanged = {ELEMENT_KEY: ElementSecurityBasis(vulnerability_ids=("CVE-2026-1",), snapshot_id="SNP@1")}
        _record_occurrence(unlocked_store, node_id, _occurrence_digest(unlocked_store, node_id, security=unchanged))

        codes = [i.code for i in verify_store(unlocked_store, basis=_basis(), security=unchanged).issues
                 if i.node_id == node_id]

        assert "W513" not in codes

    def test_a_safety_concern_judgement_is_untouched_by_a_disclosure(self, unlocked_store: Any) -> None:
        """A safety rationale never cited the snapshot, so nothing about it has stopped applying."""
        node_id = self._staged(unlocked_store, "safety")
        before = {ELEMENT_KEY: ElementSecurityBasis(vulnerability_ids=("CVE-2026-1",), snapshot_id="SNP@1")}
        _record_occurrence(unlocked_store, node_id, _occurrence_digest(unlocked_store, node_id, security=before))

        after = {ELEMENT_KEY: ElementSecurityBasis(vulnerability_ids=("CVE-2026-1", "CVE-2026-2"), snapshot_id="SNP@2")}
        codes = [i.code for i in verify_store(unlocked_store, basis=_basis(), security=after).issues
                 if i.node_id == node_id]

        assert "W513" not in codes


class TestTheTwoWayFindingsReachAReader:
    def test_a_finding_names_the_element_it_is_about(self, unlocked_store: Any) -> None:
        """A hundred findings identified only by artifact id read as a wall of `REQ@1777369067…`,
        and nobody acts on a list they cannot read. The name comes from the basis, which is the one
        place these surfaces obtain the architecture graph."""
        issues = verify_store(unlocked_store, basis=_basis()).issues
        named = [i for i in issues if i.node_id == PROVIDER_KEY]

        assert named, "the load-bearing provider produced no finding"
        assert all(i.subject_name == "" for i in named), (
            "the provider carries no name in this basis, so the finding must not invent one"
        )

    def test_a_finding_carries_a_name_the_basis_can_supply(self, unlocked_store: Any) -> None:
        from src.application.verification.assurance_two_way_coverage import (
            load_bearing_but_unanalysed,
        )

        findings = load_bearing_but_unanalysed(
            edges=_basis().edges,
            analysed_element_ids=frozenset(),
            names={PROVIDER_KEY: "Shared Provider"},
        )

        provider = next(f for f in findings if f.subject_id == PROVIDER_KEY)
        assert provider.subject_name == "Shared Provider"

    def test_a_finding_message_does_not_repeat_the_id(self, unlocked_store: Any) -> None:
        """The surface showing these leads with the element; a message that restated the id printed
        every line twice on screen."""
        from src.application.verification.assurance_two_way_coverage import (
            load_bearing_but_unanalysed,
        )

        findings = load_bearing_but_unanalysed(
            edges=_basis().edges, analysed_element_ids=frozenset(),
        )

        assert findings
        assert all(f.subject_id not in f.message for f in findings)
    def test_an_unanalysed_load_bearing_element_is_reported(self, unlocked_store: Any) -> None:
        codes = [i.code for i in verify_store(unlocked_store, basis=_basis()).issues]

        assert "W511" in codes

    def test_the_finding_carries_what_relies_on_the_element(self, unlocked_store: Any) -> None:
        """The only place the claim now appears, so an unwitnessed one cannot be checked at all."""
        reported = next(
            i for i in verify_store(unlocked_store, basis=_basis()).issues
            if i.code == "W511" and i.node_id == PROVIDER_KEY
        )

        assert reported.witness, "a load-bearing finding with no witness asserts rather than shows"
        assert any(canonical_entity_key(DEPENDENT) in step for step in reported.witness)

    def test_the_finding_goes_away_once_the_element_is_analysed(self, unlocked_store: Any) -> None:
        controller = str(unlocked_store.create_node("control-structure-node", "Provider"))
        unlocked_store.register_arch_ref(controller, PROVIDER, "binds-to")

        reported = [i for i in verify_store(unlocked_store, basis=_basis()).issues
                    if i.code == "W511" and i.node_id == PROVIDER_KEY]

        assert reported == []

    def test_none_of_it_is_reported_without_the_graph(self, unlocked_store: Any) -> None:
        """Not a pass: with no architecture model these questions cannot be asked at all."""
        codes = [i.code for i in verify_store(unlocked_store).issues]

        assert "W511" not in codes
        assert "W515" not in codes
