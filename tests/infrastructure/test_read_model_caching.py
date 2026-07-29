"""Conditional GET on model-derived reads.

The value is a 304 that costs nothing to produce; the risk is a 304 that is wrong. A stale
"not modified" is invisible to the client — it renders what it already has and never learns
the server moved on — so the validator must change whenever the answer could, and the
allowlist must exclude anything whose body depends on more than the model.
"""

from __future__ import annotations

from src.infrastructure.backend.read_model_caching import _entity_tag, _is_cacheable


class _Url:
    def __init__(self, path: str, query: str = "") -> None:
        self.path = path
        self.query = query


class _Request:
    def __init__(self, path: str, query: str = "") -> None:
        self.url = _Url(path, query)


class TestWhatMayBeCached:
    def test_model_derived_reads_qualify(self) -> None:
        assert _is_cacheable("/api/entities")
        assert _is_cacheable("/api/stats")
        assert _is_cacheable("/api/diagrams")

    def test_execution_endpoints_do_not(self) -> None:
        """An execution depends on catalogs and parameters beyond the indexed model."""
        assert not _is_cacheable("/api/viewpoints/execute")
        assert not _is_cacheable("/api/viewpoints/export-csv")

    def test_mutations_under_a_cacheable_prefix_do_not(self) -> None:
        assert not _is_cacheable("/api/entity/edit")
        assert not _is_cacheable("/api/entity/remove")

    def test_sources_outside_the_model_do_not(self) -> None:
        """Git state and the confidential store change without the model generation moving."""
        assert not _is_cacheable("/api/sync/status")
        assert not _is_cacheable("/api/assurance/stats")

    def test_an_unknown_path_is_uncached_by_default(self) -> None:
        """The list is an allowlist: a new endpoint must be reasoned about before it caches."""
        assert not _is_cacheable("/api/something-new")


class TestTheValidator:
    def test_the_same_question_against_the_same_model_matches(self) -> None:
        request = _Request("/api/entities", "domain=application")

        assert _entity_tag("gen-7", request) == _entity_tag("gen-7", _Request("/api/entities", "domain=application"))

    def test_a_new_model_generation_invalidates(self) -> None:
        request = _Request("/api/entities", "domain=application")

        assert _entity_tag("gen-7", request) != _entity_tag("gen-8", request)

    def test_a_different_query_is_a_different_answer(self) -> None:
        """Same generation, different question — sharing one tag would serve the wrong body."""
        base = _entity_tag("gen-7", _Request("/api/entities", "domain=application"))

        assert base != _entity_tag("gen-7", _Request("/api/entities", "domain=motivation"))

    def test_a_different_path_is_a_different_answer(self) -> None:
        assert _entity_tag("gen-7", _Request("/api/entities")) != _entity_tag("gen-7", _Request("/api/stats"))

    def test_the_tag_is_marked_weak(self) -> None:
        """Byte-for-byte equality is not promised — only semantic equivalence."""
        assert _entity_tag("gen-7", _Request("/api/stats")).startswith('W/"')
