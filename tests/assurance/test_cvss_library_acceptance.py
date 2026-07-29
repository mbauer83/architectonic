"""CVSS dependency-selection acceptance (§6.0(g) spike, recorded):

Library: `cvss` 3.6 (Red Hat Product Security; LGPL-3.0+ as an unmodified
runtime import — compatible with this MIT project; actively maintained).
Criteria proven here: CVSS 2.0/3.0/3.1/4.0 vector support, agreement with
official specification example vectors, and STRICT invalid-vector behavior
(typed exception — never a crash elsewhere, never a fabricated 0.0).
`packageurl-python` 0.17.6 (MIT) covers purl parsing/validation."""

from __future__ import annotations

import pytest
from cvss import CVSS2, CVSS3, CVSS4
from cvss.exceptions import CVSSError
from packageurl import PackageURL


class TestOfficialVectorAgreement:
    def test_cvss_31_specification_example(self) -> None:
        # CVE-2013-1937 style example from the v3.1 specification document.
        c = CVSS3("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N")
        assert c.scores()[0] == 5.4

    def test_cvss_30_vector(self) -> None:
        c = CVSS3("CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H")
        assert c.scores()[0] == 10.0

    def test_cvss_40_specification_example(self) -> None:
        c = CVSS4("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N")
        assert c.base_score == 9.3

    def test_cvss_20_vector(self) -> None:
        c = CVSS2("AV:N/AC:L/Au:N/C:C/I:C/A:C")
        assert c.scores()[0] == 10.0

    def test_severity_bands_match_the_specification(self) -> None:
        c = CVSS3("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N")
        assert c.severities()[0] == "Medium"


class TestStrictInvalidVectorBehavior:
    @pytest.mark.parametrize("vector", [
        "CVSS:3.1/AV:X/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",  # unknown metric value
        "CVSS:3.1/AV:N",                                   # missing mandatory metrics
        "not-a-vector",
        "",
    ])
    def test_invalid_vectors_raise_typed_errors_never_score_zero(self, vector: str) -> None:
        with pytest.raises(CVSSError):
            CVSS3(vector)

    def test_cvss4_invalid_vector_raises(self) -> None:
        with pytest.raises(CVSSError):
            CVSS4("CVSS:4.0/AV:N")


class TestPackageUrl:
    def test_purl_roundtrip_with_version(self) -> None:
        purl = PackageURL.from_string("pkg:pypi/requests@2.31.0")
        assert (purl.type, purl.name, purl.version) == ("pypi", "requests", "2.31.0")
        assert purl.to_string() == "pkg:pypi/requests@2.31.0"

    def test_versionless_purl_is_representable_for_diagnostics(self) -> None:
        purl = PackageURL.from_string("pkg:npm/leftpad")
        assert purl.version is None  # acquisition routes these to applicability-unknown

    def test_malformed_purl_raises(self) -> None:
        with pytest.raises(ValueError):
            PackageURL.from_string("definitely not a purl")
