"""Conditional GET on model-derived reads.

The value is a 304 that costs nothing to produce; the risk is a 304 that is wrong. A stale
"not modified" is invisible to the client — it renders what it already has and never learns
the server moved on — so the validator must change whenever the answer could, and the
allowlist must exclude anything whose body depends on more than the model.
"""

from __future__ import annotations

from pathlib import Path

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
        """A mutation shares its address with the cacheable read now that identity is in the path,
        so eligibility cannot be decided from the path alone — the middleware only ever considers a
        GET, and these are the paths that prove why."""
        assert not _is_cacheable("/api/entities/APP@1.ab.thing/context/edit")

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


# ── the promise an ETag makes, across processes ──────────────────────────────


def test_two_processes_never_agree_on_a_tag_for_the_same_generation() -> None:
    """An ETag promises that the same tag means the same body, and the generation counter alone
    cannot keep that promise: it starts again at zero in every process.

    A client holding the tag for generation 7 from yesterday's process was told 304 by today's,
    whose generation 7 describes different content — and a stale 304 is invisible. It cost a running
    GUI its view of a recorded change: the artifact carried one and went on saying it did not, for as
    long as the browser held the tag.
    """
    import subprocess
    import sys

    def tag_from_a_fresh_process() -> str:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-c",
             "from src.infrastructure.artifact_index.versioning import build_read_model_etag;"
             "print(build_read_model_etag('scope', 7))"],
            capture_output=True, text=True, check=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        ).stdout.strip()

    assert tag_from_a_fresh_process() != tag_from_a_fresh_process()


def test_one_process_answers_the_same_tag_for_the_same_generation() -> None:
    """The other half: within a process the tag is stable, or nothing would ever revalidate."""
    from src.infrastructure.artifact_index.versioning import build_read_model_etag

    assert build_read_model_etag("scope", 7) == build_read_model_etag("scope", 7)


def test_a_later_generation_is_a_different_tag() -> None:
    from src.infrastructure.artifact_index.versioning import build_read_model_etag

    assert build_read_model_etag("scope", 7) != build_read_model_etag("scope", 8)


def test_two_scopes_do_not_share_a_tag() -> None:
    from src.infrastructure.artifact_index.versioning import build_read_model_etag

    assert build_read_model_etag("one", 7) != build_read_model_etag("two", 7)
