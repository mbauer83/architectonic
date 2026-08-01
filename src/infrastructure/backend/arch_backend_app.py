"""FastAPI application construction for the arch backend."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from mcp.server.fastmcp.server import StreamableHTTPASGIApp

from src.config.settings import request_thread_dump_seconds, slow_request_warning_seconds
from src.infrastructure.artifact_index.coordination import get_write_queue_state_snapshot
from src.infrastructure.backend._teardown import teardown_steps
from src.infrastructure.backend.cache_directive import apply_cache_directive
from src.infrastructure.backend.read_model_caching import conditional_read_middleware
from src.infrastructure.backend.shutdown import run_teardown
from src.infrastructure.mcp.artifact_mcp import auto_start_default_watcher
from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read, mcp_assurance_write
from src.infrastructure.rest.routers import state as gui_state

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.infrastructure.git.git_auth import GitCredentials
    from src.infrastructure.git.git_sync import RepoSpec


def find_git_repos() -> "list[RepoSpec]":
    """Return git-backed repos from arch-workspace.yaml, tagged with their role."""
    from src.config.workspace_paths import find_workspace_config, parse_workspace_config
    from src.infrastructure.git.git_sync import RepoSpec

    cfg = find_workspace_config(Path.cwd())
    if cfg is None:
        return []
    workspace_root = cfg.parent
    config = parse_workspace_config(cfg)
    repos = []
    for key in ("engagement", "enterprise"):
        spec = config.get(key, {})
        if "git" in spec:
            git_spec = spec["git"]
            rel = git_spec.get("path", f"./{key}-repository")
            repos.append(
                RepoSpec(
                    path=(workspace_root / rel).resolve(),
                    role=key,  # type: ignore[arg-type]
                )
            )
    return repos


def _log_thread_dump(*, reason: str) -> None:
    frames = sys._current_frames()
    threads = {thread.ident: thread for thread in threading.enumerate()}
    lines = [f"=== thread dump: {reason} ==="]
    for ident, frame in frames.items():
        thread = threads.get(ident)
        name = thread.name if thread is not None else "unknown"
        lines.append(f"--- thread ident={ident} name={name} ---")
        lines.extend(line.rstrip("\n") for line in traceback.format_stack(frame))
    logger.warning("\n".join(lines))


def _log_slow_request_warning(*, method: str, path: str, threshold_s: float) -> None:
    queue_state = get_write_queue_state_snapshot()
    logger.warning(
        "HTTP request still running method=%s path=%s threshold_s=%.1f "
        "active_jobs=%s pending_jobs=%s active_tool=%s active_operation_id=%s active_phase=%s",
        method,
        path,
        threshold_s,
        queue_state["active_jobs"],
        queue_state["pending_jobs"],
        queue_state["active_tool_name"],
        queue_state["active_operation_id"],
        queue_state["active_phase"],
    )


def _log_structured_output_tool_inventory() -> None:
    """Log structured-output tool counts at startup for observability."""
    read_tools = mcp_read._tool_manager.list_tools()  # type: ignore[attr-defined]
    write_tools = mcp_write._tool_manager.list_tools()  # type: ignore[attr-defined]
    read_structured = [t.name for t in read_tools if t.output_schema is not None]
    write_structured = [t.name for t in write_tools if t.output_schema is not None]
    if read_structured:
        logger.info(
            "Read server: %d structured-output tools: %s",
            len(read_structured),
            ", ".join(read_structured),
        )
    else:
        logger.warning("Read server has no structured-output tools — normalizer may not be installed")
    if write_structured:
        logger.info(
            "Write server: %d structured-output tools: %s",
            len(write_structured),
            ", ".join(write_structured),
        )


def _request_watchdogs(method: str, path: str) -> tuple[threading.Timer, threading.Timer]:
    """Two daemon timers that warn on a slow request and dump threads on a stuck one.

    Both are started per request and cancelled when it completes, so in the normal case
    neither fires. The thresholds are operational tuning, not domain values: they live in
    `backend.slow_request_warning_s` / `backend.request_thread_dump_s` in settings, beside
    the port and log level, rather than as constants here.
    """
    warning_s = slow_request_warning_seconds()
    dump_s = request_thread_dump_seconds()
    slow = threading.Timer(
        warning_s,
        _log_slow_request_warning,
        kwargs={"method": method, "path": path, "threshold_s": warning_s},
    )
    dump = threading.Timer(
        dump_s,
        _log_thread_dump,
        kwargs={"reason": (f"request still running after {dump_s:.1f}s method={method} path={path}")},
    )
    for timer in (slow, dump):
        timer.daemon = True
        timer.start()
    return slow, dump


async def _log_requests(request, call_next):  # type: ignore[no-untyped-def]
    """HTTP middleware: log start/end, time the request, and arm slow/stuck watchdogs."""
    started = time.perf_counter()
    method, path = request.method, request.url.path
    slow_watchdog, dump_watchdog = _request_watchdogs(method, path)
    logger.info("HTTP request started method=%s path=%s", method, path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "HTTP request failed method=%s path=%s duration_ms=%.1f",
            method, path, (time.perf_counter() - started) * 1000.0,
        )
        raise
    finally:
        slow_watchdog.cancel()
        dump_watchdog.cancel()
    logger.info(
        "HTTP request completed method=%s path=%s status=%s duration_ms=%.1f",
        method, path, response.status_code, (time.perf_counter() - started) * 1000.0,
    )
    return response


async def _on_repo_changed(repo_path: Path) -> None:
    """Refresh the artifact index and notify GUI clients after a git pull or merge."""
    repo = gui_state.maybe_get_repo()
    if repo is not None:
        await asyncio.to_thread(repo.refresh)
    from src.infrastructure.rest.routers.events import event_bus  # noqa: PLC0415
    from src.infrastructure.rest.routers.sync.status_cache import invalidate_sync_status_cache  # noqa: PLC0415

    invalidate_sync_status_cache(repo=repo_path)
    await event_bus.publish({
        "type": "sync_repository_updated",
        "repo": str(repo_path),
        "label": "Repository updated — refreshing view…",
    })


async def _health_check():  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    managers = {
        "read_tools": mcp_read, "write_tools": mcp_write,
        "assurance_read_tools": mcp_assurance_read, "assurance_write_tools": mcp_assurance_write,
    }
    counts = {key: mgr._tool_manager.list_tools() for key, mgr in managers.items()}  # type: ignore[attr-defined]
    structured = [t.name for t in counts["read_tools"] if t.output_schema is not None]
    return JSONResponse({
        "status": "ok",
        **{key: len(tools) for key, tools in counts.items()},
        "structured_output_tools": len(structured),
        "structured_output_tool_names": structured,
    })


def _document_version() -> str:
    """The OpenAPI document's version, read from package metadata.

    Read rather than declared: the two were maintained separately and had already diverged — the
    document claimed 0.3.0 against a 0.1.0 package — so a client that pinned the document version
    was pinning a number nothing produced.
    """
    from importlib.metadata import PackageNotFoundError  # noqa: PLC0415
    from importlib.metadata import version as package_version  # noqa: PLC0415

    try:
        return package_version("architectonic")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _build_app(credentials: "GitCredentials | None" = None):  # type: ignore[no-untyped-def]
    from fastapi import Depends, FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.contracts.error_responses import install_error_contracts
    from src.infrastructure.rest.contracts.identity_resolution import (
        reject_repeated_scalar_query_parameters,
    )
    from src.infrastructure.rest.contracts.operation_ids import manifest_operation_id
    from src.infrastructure.rest.contracts.wire_nulls import install_wire_null_policy
    from src.infrastructure.rest.routers._openapi import APP_RESPONSES
    from src.infrastructure.rest.routers.admin import router as admin_router
    from src.infrastructure.rest.routers.assurance.router import router as assurance_router
    from src.infrastructure.rest.routers.authoring_guidance import router as authoring_guidance_router
    from src.infrastructure.rest.routers.connections.router import router as connections_router
    from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
    from src.infrastructure.rest.routers.diagrams.types import router as diagram_types_router
    from src.infrastructure.rest.routers.documents import router as documents_router
    from src.infrastructure.rest.routers.entities.router import router as entities_router
    from src.infrastructure.rest.routers.entities.search import router as entity_search_router
    from src.infrastructure.rest.routers.events import router as events_router
    from src.infrastructure.rest.routers.groups import router as groups_router
    from src.infrastructure.rest.routers.identifiers import router as identifiers_router
    from src.infrastructure.rest.routers.modules import router as modules_router
    from src.infrastructure.rest.routers.promote import router as promote_router
    from src.infrastructure.rest.routers.sync.router import router as sync_router
    from src.infrastructure.rest.routers.viewpoints.authoring import router as viewpoint_authoring_router
    from src.infrastructure.rest.routers.viewpoints.router import router as viewpoints_router

    mcp_read.streamable_http_app()
    mcp_write.streamable_http_app()
    mcp_assurance_read.streamable_http_app()
    mcp_assurance_write.streamable_http_app()

    read_app = StreamableHTTPASGIApp(mcp_read.session_manager)
    write_app = StreamableHTTPASGIApp(mcp_write.session_manager)
    assurance_read_app = StreamableHTTPASGIApp(mcp_assurance_read.session_manager)
    assurance_write_app = StreamableHTTPASGIApp(mcp_assurance_write.session_manager)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with AsyncExitStack() as stack:
            logger.info("Starting MCP session managers")
            await stack.enter_async_context(mcp_read.session_manager.run())
            await stack.enter_async_context(mcp_write.session_manager.run())
            await stack.enter_async_context(mcp_assurance_read.session_manager.run())
            await stack.enter_async_context(mcp_assurance_write.session_manager.run())
            from src.infrastructure.mcp.artifact_mcp.write_queue import attach_event_loop

            attach_event_loop(asyncio.get_running_loop())
            auto_start_default_watcher()
            logger.info("Default watcher auto-started")
            _log_structured_output_tool_inventory()

            git_repos = find_git_repos()
            sync_mgr = None
            if git_repos:
                from src.infrastructure.git.git_sync import GitSyncManager

                logger.info(
                    "Starting git-sync for repos: %s",
                    ", ".join(f"{r.path}({r.role})" for r in git_repos),
                )
                from src.infrastructure.rest.routers.sync.status_cache import invalidate_sync_status_cache

                sync_mgr = GitSyncManager(
                    git_repos,
                    credentials=credentials,
                    on_repo_changed=_on_repo_changed,
                    on_health_changed=lambda repo: invalidate_sync_status_cache(repo=repo),
                )
                await sync_mgr.start()
            else:
                logger.info("No git-backed repositories configured for sync")

            yield

            await run_teardown(teardown_steps(sync_mgr))
            logger.info("Backend lifespan shutdown complete")

    app = FastAPI(
        title="Architecture Repository Backend",
        version=_document_version(),
        lifespan=lifespan,
        generate_unique_id_function=manifest_operation_id,
        responses=APP_RESPONSES,
        # An incomplete detail path is not a collection: `/api/entities/` names an entity whose
        # identifier is missing, and redirecting it to the collection answers a different question
        # than the one asked, hiding the caller's bug until something depends on the wrong answer.
        redirect_slashes=False,
        dependencies=[Depends(reject_repeated_scalar_query_parameters)],
    )
    install_module_registry(app)

    # Registered after _log_requests so a 304 is still logged and timed.
    app.middleware("http")(conditional_read_middleware)
    # Outside the conditional-read middleware, so a 304 keeps the `no-cache` it chose and every
    # other response gets its operation's declared directive rather than none.
    app.middleware("http")(apply_cache_directive)
    app.middleware("http")(_log_requests)
    # The typed error envelope and the request id every error carries. Registered last so its
    # middleware is outermost and a failure anywhere inside still produces an envelope.
    install_error_contracts(app)
    # The published document states what the wire actually carries: a DTO served only by
    # null-omitting routes has its optionals declared absent-or-value rather than nullable, so the
    # generated types are an oracle the frontend's decoders can be held against. Installed here and
    # not after the routers because generation is lazy — nothing has asked for the document yet.
    install_wire_null_policy(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_api_route("/health", _health_check, include_in_schema=False)

    for router in (
        entities_router, entity_search_router, connections_router, diagram_types_router,
        diagrams_router, documents_router, groups_router, identifiers_router, modules_router, promote_router,
        sync_router, admin_router, events_router, assurance_router, authoring_guidance_router,
        viewpoints_router, viewpoint_authoring_router,
    ):
        app.include_router(router)

    # Starlette mounts only match `/mcp/…`, not the bare `/mcp` path. Serve each MCP ASGI
    # handler on both variants so IDE clients can POST to `/mcp` without being routed into
    # the SPA/static handler.
    mcp_routes = {
        "read": read_app, "write": write_app,
        "assurance-read": assurance_read_app, "assurance-write": assurance_write_app,
    }
    for name, asgi_app in mcp_routes.items():
        for suffix in (f"/mcp/{name}", f"/mcp/{name}/"):
            app.add_route(suffix, cast(object, asgi_app), include_in_schema=False)  # type: ignore[arg-type]

    # repo root is four levels up: backend → infrastructure → src → <repo>
    gui_dist = Path(__file__).resolve().parents[3] / "tools" / "gui" / "dist"
    if gui_dist.exists():
        # SPA history-fallback: deep links (e.g. /entities/groups) have no file on disk, so
        # serve index.html and let the client router resolve them.
        from src.infrastructure.backend._spa_static import SPAStaticFiles  # noqa: PLC0415

        app.mount("/", SPAStaticFiles(directory=str(gui_dist), html=True), name="static")
    return app
