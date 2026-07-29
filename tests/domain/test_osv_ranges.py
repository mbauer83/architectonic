"""OSV affected-range semantics: introduced/fixed/last_affected/limit events,
ecosystem comparison adapters (PyPI + npm incl. pre-release ordering), exact
version lists, commit ranges as provenance-only, and unknown-not-silent-drop."""

from __future__ import annotations

from src.domain.assurance.osv_ranges import evaluate_applicability


def _entry(events: list[dict[str, str]], *, range_type: str = "ECOSYSTEM",
           versions: list[str] | None = None) -> dict[str, object]:
    entry: dict[str, object] = {"ranges": [{"type": range_type, "events": events}]}
    if versions is not None:
        entry["versions"] = versions
    return entry


class TestEventSemantics:
    RANGE = [{"introduced": "2.0.0"}, {"fixed": "2.31.1"}]

    def test_inside_the_interval_is_applicable(self) -> None:
        assert evaluate_applicability("pypi", "2.31.0", [_entry(self.RANGE)]) == "applicable"

    def test_fixed_bound_is_exclusive(self) -> None:
        assert evaluate_applicability("pypi", "2.31.1", [_entry(self.RANGE)]) == "not_applicable"

    def test_below_introduced_is_not_applicable(self) -> None:
        assert evaluate_applicability("pypi", "1.9.0", [_entry(self.RANGE)]) == "not_applicable"

    def test_last_affected_bound_is_inclusive(self) -> None:
        rng = [{"introduced": "0"}, {"last_affected": "2.31.0"}]
        assert evaluate_applicability("pypi", "2.31.0", [_entry(rng)]) == "applicable"
        assert evaluate_applicability("pypi", "2.31.1", [_entry(rng)]) == "not_applicable"

    def test_introduced_zero_means_from_the_beginning(self) -> None:
        rng = [{"introduced": "0"}, {"fixed": "1.0.0"}]
        assert evaluate_applicability("pypi", "0.0.1", [_entry(rng)]) == "applicable"

    def test_limit_caps_the_interval_exclusively(self) -> None:
        rng = [{"introduced": "1.0.0"}, {"limit": "2.0.0"}]
        assert evaluate_applicability("pypi", "1.5.0", [_entry(rng)]) == "applicable"
        assert evaluate_applicability("pypi", "2.0.0", [_entry(rng)]) == "not_applicable"


class TestEcosystemAdapters:
    def test_pypi_understands_pep440_orderings(self) -> None:
        rng = [{"introduced": "2.0.0"}, {"fixed": "2.0.0.post1"}]
        assert evaluate_applicability("pypi", "2.0.0", [_entry(rng)]) == "applicable"

    def test_npm_prerelease_sorts_before_release(self) -> None:
        rng = [{"introduced": "1.0.0-alpha"}, {"fixed": "1.0.0"}]
        assert evaluate_applicability("npm", "1.0.0-beta.2", [_entry(rng)]) == "applicable"
        assert evaluate_applicability("npm", "1.0.0", [_entry(rng)]) == "not_applicable"

    def test_unparsable_version_is_unknown_never_dropped(self) -> None:
        rng = [{"introduced": "1.0.0"}, {"fixed": "2.0.0"}]
        assert evaluate_applicability("npm", "not-a-version", [_entry(rng)]) == "unknown"

    def test_unknown_ecosystem_is_unknown(self) -> None:
        rng = [{"introduced": "1.0"}, {"fixed": "2.0"}]
        assert evaluate_applicability("cargo", "1.5", [_entry(rng)]) == "unknown"


class TestOtherSignals:
    def test_exact_version_list_membership_wins(self) -> None:
        entry = _entry([], versions=["1.2.3", "1.2.4"])
        assert evaluate_applicability("pypi", "1.2.3", [entry]) == "applicable"
        assert evaluate_applicability("pypi", "1.2.5", [entry]) == "not_applicable"

    def test_commit_ranges_are_provenance_only(self) -> None:
        git_only = {"ranges": [{"type": "GIT", "events": [
            {"introduced": "abc123"}, {"fixed": "def456"},
        ]}]}
        assert evaluate_applicability("pypi", "1.0.0", [git_only]) == "unknown"

    def test_no_signal_at_all_is_unknown(self) -> None:
        assert evaluate_applicability("pypi", "1.0.0", [{}]) == "unknown"
