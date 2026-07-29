"""Bounded, generation-keyed memoization of read-tool results.

Two failure modes, opposite in kind. Serving a stale answer is a correctness fault and must
be impossible: the generation is part of the lookup, so a newer model always misses rather
than relying on eviction to have happened. Growing without limit is an availability fault:
one whole-repository listing is megabytes, so both the size of a single entry and the number
of retained entries are capped, and exceeding either must degrade to "compute and serve",
never to "store anyway" or "fail".
"""

from __future__ import annotations

from src.infrastructure.mcp.artifact_mcp.read_result_cache import ReadResultCache


def _counter():  # type: ignore[no-untyped-def]
    calls = {"n": 0}

    def compute():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return {"value": calls["n"]}

    return calls, compute


class TestCorrectness:
    def test_a_repeat_question_is_served_from_the_cache(self) -> None:
        cache = ReadResultCache()
        calls, compute = _counter()

        first = cache.get_or_compute("t", {"a": 1}, 7, compute)
        second = cache.get_or_compute("t", {"a": 1}, 7, compute)

        assert first == second
        assert calls["n"] == 1

    def test_a_new_generation_never_serves_the_old_answer(self) -> None:
        """The property the whole design rests on."""
        cache = ReadResultCache()
        calls, compute = _counter()

        cache.get_or_compute("t", {"a": 1}, 7, compute)
        again = cache.get_or_compute("t", {"a": 1}, 8, compute)

        assert calls["n"] == 2
        assert again == {"value": 2}

    def test_different_arguments_are_different_questions(self) -> None:
        cache = ReadResultCache()
        calls, compute = _counter()

        cache.get_or_compute("t", {"a": 1}, 7, compute)
        cache.get_or_compute("t", {"a": 2}, 7, compute)

        assert calls["n"] == 2

    def test_argument_order_is_not_a_different_question(self) -> None:
        cache = ReadResultCache()
        calls, compute = _counter()

        cache.get_or_compute("t", {"a": 1, "b": 2}, 7, compute)
        cache.get_or_compute("t", {"b": 2, "a": 1}, 7, compute)

        assert calls["n"] == 1

    def test_different_tools_do_not_share_entries(self) -> None:
        cache = ReadResultCache()
        calls, compute = _counter()

        cache.get_or_compute("one", {}, 7, compute)
        cache.get_or_compute("two", {}, 7, compute)

        assert calls["n"] == 2

    def test_an_unknown_generation_is_never_stored(self) -> None:
        """With nothing to invalidate against, caching would be unbounded in time."""
        cache = ReadResultCache()
        calls, compute = _counter()

        cache.get_or_compute("t", {}, None, compute)
        cache.get_or_compute("t", {}, None, compute)

        assert calls["n"] == 2
        assert cache.stats().entries == 0


class TestBounds:
    def test_an_oversized_result_is_served_but_not_stored(self) -> None:
        cache = ReadResultCache(max_entry_bytes=256)
        big = {"rows": ["x" * 200 for _ in range(50)]}

        first = cache.get_or_compute("t", {}, 7, lambda: big)
        second = cache.get_or_compute("t", {}, 7, lambda: big)

        assert first is big and second is big
        assert cache.stats().entries == 0
        assert cache.stats().too_large == 2

    def test_the_entry_count_is_capped(self) -> None:
        cache = ReadResultCache(max_entries=4)

        for i in range(20):
            cache.get_or_compute("t", {"i": i}, 7, lambda: {"v": 1})

        assert cache.stats().entries == 4

    def test_eviction_is_least_recently_used(self) -> None:
        cache = ReadResultCache(max_entries=2)
        cache.get_or_compute("t", {"i": 1}, 7, lambda: {"v": 1})
        cache.get_or_compute("t", {"i": 2}, 7, lambda: {"v": 2})
        # Touch 1 so 2 becomes the least recently used.
        cache.get_or_compute("t", {"i": 1}, 7, lambda: {"v": 99})
        cache.get_or_compute("t", {"i": 3}, 7, lambda: {"v": 3})

        recomputed: list[str] = []
        cache.get_or_compute("t", {"i": 1}, 7, lambda: recomputed.append("1") or {"v": 0})
        cache.get_or_compute("t", {"i": 2}, 7, lambda: recomputed.append("2") or {"v": 0})

        assert recomputed == ["2"], "the most recently used entry should have survived"

    def test_clear_drops_everything(self) -> None:
        cache = ReadResultCache()
        cache.get_or_compute("t", {}, 7, lambda: {"v": 1})

        cache.clear()

        assert cache.stats().entries == 0


class TestInstallation:
    """Wrapping happens over the registered tools, and only the ones that qualify."""

    def _registered(self):  # type: ignore[no-untyped-def]
        from mcp.server.fastmcp import FastMCP

        from src.infrastructure.mcp.artifact_mcp.register_query_tools import register_query_tools

        mcp = FastMCP("test")
        register_query_tools(mcp)
        return mcp

    def test_every_cacheable_name_exists_in_the_registry(self) -> None:
        """A renamed tool would silently stop being cached; the list has to track the registry."""
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import CACHEABLE_READ_TOOLS

        registered = set(self._registered()._tool_manager._tools)  # noqa: SLF001

        assert CACHEABLE_READ_TOOLS <= registered, CACHEABLE_READ_TOOLS - registered

    def test_a_wrapped_tool_serves_a_repeat_call_from_the_cache(self) -> None:
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import install_read_result_cache

        calls = {"n": 0}

        def stats(**_: object) -> dict[str, int]:
            """Original."""
            calls["n"] += 1
            return {"n": calls["n"]}

        class _Tool:
            fn = staticmethod(stats)
            is_async = False

        class _Mcp:
            _tool_manager = type("M", (), {"_tools": {"artifact_query_stats": _Tool()}})()

        mcp = _Mcp()
        cache = ReadResultCache()
        assert install_read_result_cache(mcp, cache) == 1

        wrapped = mcp._tool_manager._tools["artifact_query_stats"].fn  # noqa: SLF001
        assert wrapped.__doc__ == "Original.", "the wrapper must keep the tool's schema-visible docstring"

        import src.infrastructure.mcp.artifact_mcp.install_read_cache as module

        original = module.generation_for
        module.generation_for = lambda _arguments: 42  # type: ignore[assignment]
        try:
            first = wrapped()
            second = wrapped()
        finally:
            module.generation_for = original  # type: ignore[assignment]

        assert first == second == {"n": 1}
        assert calls["n"] == 1
        assert cache.stats().hits == 1

    def test_the_viewpoint_tool_is_never_wrapped(self) -> None:
        """Its catalog is reloaded per request and is not covered by the model generation."""
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import CACHEABLE_READ_TOOLS

        assert "artifact_query_viewpoint" not in CACHEABLE_READ_TOOLS
        assert "artifact_verify" not in CACHEABLE_READ_TOOLS

    def test_an_unrecognised_manager_disables_caching_rather_than_failing(self) -> None:
        """The cache is an optimisation; losing it must not take the read surface with it."""
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import install_read_result_cache

        class _Odd:
            _tool_manager = object()

        assert install_read_result_cache(_Odd(), ReadResultCache()) == 0

    def test_a_positional_call_reaches_the_tool(self) -> None:
        """The wrapper stands in for the tool's own signature, so it must accept its calls."""
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import install_read_result_cache

        def read(entity_id: str, repo_root: str | None = None) -> dict[str, str]:
            return {"id": entity_id, "root": str(repo_root)}

        class _Tool:
            fn = staticmethod(read)
            is_async = False

        tools = {"artifact_query_read_artifact": _Tool()}
        mcp = type("M", (), {"_tool_manager": type("T", (), {"_tools": tools})()})()
        install_read_result_cache(mcp, ReadResultCache())

        wrapped = tools["artifact_query_read_artifact"].fn

        assert wrapped("E@1", repo_root="/tmp") == {"id": "E@1", "root": "/tmp"}

    def test_positional_and_keyword_forms_are_one_question(self) -> None:
        import src.infrastructure.mcp.artifact_mcp.install_read_cache as module
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import install_read_result_cache

        calls = {"n": 0}

        def read(entity_id: str) -> int:
            calls["n"] += 1
            return calls["n"]

        class _Tool:
            fn = staticmethod(read)
            is_async = False

        tools = {"artifact_query_read_artifact": _Tool()}
        mcp = type("M", (), {"_tool_manager": type("T", (), {"_tools": tools})()})()
        install_read_result_cache(mcp, ReadResultCache())
        wrapped = tools["artifact_query_read_artifact"].fn

        original = module.generation_for
        module.generation_for = lambda _arguments: 7  # type: ignore[assignment]
        try:
            assert wrapped("E@1") == 1
            assert wrapped(entity_id="E@1") == 1
        finally:
            module.generation_for = original  # type: ignore[assignment]

        assert calls["n"] == 1


class TestGenerationScoping:
    """A stamp may only validate results the stamped index can actually see."""

    def test_an_unresolvable_repo_is_never_cached(self) -> None:
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import generation_for

        assert generation_for({"repo_root": "\x00 not a path", "repo_scope": "engagement"}) is None

    def test_the_stamp_comes_from_the_index_the_call_resolves_to(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Two roots, two indexes: their generations must not be interchangeable."""
        from src.infrastructure.artifact_index import shared_artifact_index
        from src.infrastructure.mcp.artifact_mcp.install_read_cache import generation_for

        root = tmp_path / "engagements" / "ENG-STAMP" / "architecture-repository"
        (root / "model").mkdir(parents=True)
        index = shared_artifact_index([root])
        index.refresh()
        before = generation_for({"repo_root": str(root), "repo_scope": "engagement"})
        assert before is not None

        index.refresh()

        assert generation_for({"repo_root": str(root), "repo_scope": "engagement"}) != before
