"""A factor judgement may not be recorded against a basis the process could not assemble.

`record_factor_assessment` already refuses an *empty* digest, and its reason is exact: without a basis
there is nothing to say when the judgement stops applying, so it would apply forever. There is a
second way to have no basis, and it fails the other direction — the judgement applies *never*.

`read_architecture_basis` returns the empty `ArchitectureBasis()` when the architecture model or the
connection types are unreachable, which the surfaces need in order to stay usable standalone. Its
occurrence digest was then `compute_basis_digest([])`, a perfectly well-formed hash, and a judgement
recorded against it was born superseded: the first reader that could see the model computed a
different digest and the derived value stood again.

Eleven judgements in the shipped store were in that state, each with a written rationale, and none had
ever applied. Nothing said so — the finding for a retired judgement reads *made against a picture that
has since changed*, which sends a reader looking for a change to the model that never happened.

**`digest([])` cannot be the marker.** An element with no connections in a fully assembled basis
legitimately cites no facts and hashes to exactly that value, so refusing the hash would refuse a
correct judgement about an isolated element. The distinction is whether the basis was *assembled*,
which the basis now carries, and an unassembled one yields a token that is not a hash at all.
"""

from __future__ import annotations

from src.application.assurance.fmea_architecture import ArchitectureBasis, read_architecture_basis
from src.application.assurance.fmea_derivation import derive_factors
from src.domain.assurance.fmea_factors import UNGROUNDED_BASIS, compute_basis_digest, is_grounded


class TestTheMarkerIsNotAHash:
    def test_it_is_not_the_digest_of_an_empty_basis(self) -> None:
        """The whole point: an isolated element in a real basis hashes to that, and its judgement
        is legitimate."""
        assert UNGROUNDED_BASIS != compute_basis_digest([])

    def test_it_is_not_grounded(self) -> None:
        assert not is_grounded(UNGROUNDED_BASIS)

    def test_a_real_digest_is_grounded(self) -> None:
        assert is_grounded(compute_basis_digest([]))
        assert is_grounded(compute_basis_digest(["some cited fact"]))

    def test_an_absent_digest_is_not_grounded(self) -> None:
        assert not is_grounded("")
        assert not is_grounded("   ")


class TestWhatTheDerivationReportsForAnUnknownBasis:
    def test_an_unassembled_basis_yields_the_marker(self) -> None:
        derived = derive_factors("FMD@1.a.b", nodes=[], edges=[], occurrence_basis=None)

        assert derived.digests["occurrence"] == UNGROUNDED_BASIS

    def test_an_assembled_basis_with_no_facts_yields_a_hash(self) -> None:
        """Empty is not unknown, and the two must not collapse."""
        derived = derive_factors("FMD@1.a.b", nodes=[], edges=[], occurrence_basis=())

        assert derived.digests["occurrence"] == compute_basis_digest([])

    def test_the_store_derived_factors_are_unaffected(self) -> None:
        """Severity and detectability are derived from the assurance graph, which is present
        whatever the architecture model is doing. Only occurrence cites the architecture."""
        unknown = derive_factors("FMD@1.a.b", nodes=[], edges=[], occurrence_basis=None)
        known = derive_factors("FMD@1.a.b", nodes=[], edges=[], occurrence_basis=())

        assert unknown.digests["severity"] == known.digests["severity"]
        assert unknown.digests["detectability"] == known.digests["detectability"]


class TestTheBasisSaysWhetherItWasAssembled:
    def test_the_empty_default_was_not(self) -> None:
        assert not ArchitectureBasis().assembled

    def test_a_basis_built_without_a_model_was_not(self) -> None:
        assert not read_architecture_basis(None).assembled

    def test_a_basis_built_without_connection_types_was_not(self) -> None:
        """Both inputs are required to assemble one, and either missing yields the empty basis."""
        assert not read_architecture_basis(object(), connection_types=None).assembled


class TestTheWriteRefusesIt:
    """The guard that stops it recurring. Stated over the use case, since the tool passes the digest
    straight through and validates nothing about it itself."""

    def _refusal(self, digest: str):
        from src.application.assurance.fmea_factors import (
            RecordFactorRequest,
            record_factor_assessment,
        )

        class _Unlocked:
            def is_unlocked(self) -> bool:
                return True

            def get_node(self, node_id: str) -> None:
                return None

        return record_factor_assessment(
            RecordFactorRequest(
                node_id="FMD@1.a.b", factor="occurrence", value="unlikely",
                justification="one report in two years", author="analyst", basis_digest=digest,
            ),
            store=_Unlocked(),  # type: ignore[arg-type]
            archive=None,  # type: ignore[arg-type]
        )

    def test_the_ungrounded_marker_is_rejected(self) -> None:
        from src.application.assurance.fmea_factors import FactorInvalid

        result = self._refusal(UNGROUNDED_BASIS)

        assert isinstance(result, FactorInvalid)
        assert [e.field for e in result.errors] == ["basis_digest"]

    def test_the_refusal_says_why_there_is_no_digest_to_use(self) -> None:
        """A caller told only "required" would send the marker back; the message has to name the
        cause, which is a report assembled without the architecture model."""
        from src.application.assurance.fmea_factors import FactorInvalid

        result = self._refusal(UNGROUNDED_BASIS)

        assert isinstance(result, FactorInvalid)
        assert "architecture model" in result.errors[0].message

    def test_an_absent_digest_is_still_rejected(self) -> None:
        from src.application.assurance.fmea_factors import FactorInvalid

        assert isinstance(self._refusal("   "), FactorInvalid)

    def test_a_real_digest_gets_past_this_guard(self) -> None:
        """It fails on the node lookup instead, which is what proves the basis guard let it through
        rather than the request being malformed some other way."""
        from src.application.assurance.fmea_factors import FactorNodeNotFound

        assert isinstance(self._refusal(compute_basis_digest(["a fact"])), FactorNodeNotFound)
