"""An asset is installed only when its bytes agree with every digest stated for it."""

from __future__ import annotations

import pytest

from src.application.software_update.release import (
    ChecksumStatement,
    ReleaseAsset,
    sha256_of,
    verify_asset,
)

DATA = b"the bundle"
GOOD = sha256_of(DATA)
BAD = "0" * 64


def _asset(stated: str | None) -> ReleaseAsset:
    return ReleaseAsset("architectonic-gui-0.10.1.tar.gz", "https://example.invalid/a.tgz", stated, len(DATA))


class TestReadingTheChecksumFile:
    def test_reads_the_form_sha256sum_writes_in_text_and_binary_mode(self) -> None:
        statement = ChecksumStatement.parse(f"{GOOD}  a.tar.gz\n{GOOD.upper()} *b.tar.gz\n\n")

        assert statement.digest_of("a.tar.gz") == GOOD
        assert statement.digest_of("b.tar.gz") == GOOD
        assert statement.digest_of("c") is None

    @pytest.mark.parametrize("line", ["notadigest  a.tar.gz", f"{GOOD} a.tar.gz", f"{GOOD}", "a.tar.gz  " + GOOD])
    def test_refuses_a_line_that_is_not_a_checksum_line(self, line: str) -> None:
        with pytest.raises(ValueError):
            ChecksumStatement.parse(line)


class TestVerifyingBytes:
    def test_agreement_with_both_statements_verifies(self) -> None:
        verification = verify_asset(DATA, _asset(f"sha256:{GOOD}"), ChecksumStatement({_asset(None).name: GOOD}))

        assert verification.ok
        assert set(verification.checked_against) == {"release", "SHA256SUMS"}

    def test_one_statement_is_enough_when_it_agrees(self) -> None:
        assert verify_asset(DATA, _asset(None), ChecksumStatement({_asset(None).name: GOOD})).ok
        assert verify_asset(DATA, _asset(GOOD), None).ok

    def test_disagreement_with_either_statement_refuses_and_names_the_source(self) -> None:
        by_release = verify_asset(DATA, _asset(BAD), ChecksumStatement({_asset(None).name: GOOD}))
        by_build = verify_asset(DATA, _asset(GOOD), ChecksumStatement({_asset(None).name: BAD}))

        assert by_release.verdict == "digest_mismatch" and "release" in by_release.detail
        assert by_build.verdict == "digest_mismatch" and "SHA256SUMS" in by_build.detail

    def test_no_statement_at_all_is_a_refusal_not_a_pass(self) -> None:
        verification = verify_asset(DATA, _asset(None), None)

        assert verification.verdict == "no_statement"
        assert not verification.ok
