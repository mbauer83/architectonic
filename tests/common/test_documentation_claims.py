"""Documentation drift detector: everything the docs NAME must actually exist.

Prose goes stale silently. A page can describe a CLI command, an HTTP endpoint, or
an MCP tool that was renamed or deleted, and nothing fails — the reader discovers
it by typing the command and getting an error. Three real instances were found by
hand in one sitting: `arch-assurance import-sbom` documented in two pages though it
has never existed, and a capability inventory still listing adapters deleted a
month earlier.

These tests close that loop by resolving documented names against the running
code. They are deliberately about EXISTENCE, not correctness of description: a
wrong explanation is a review problem, but a name that resolves to nothing is
mechanically detectable and should never survive a commit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"


def _doc_files() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def _docs_text() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in _doc_files()}


# ── HTTP endpoints ────────────────────────────────────────────────────────────


def _registered_paths() -> set[str]:
    """Every route path the GUI routers declare.

    Collected from the router modules rather than by constructing the app: the
    app factory discovers git repositories and starts background work, none of
    which a documentation check should trigger.
    """
    import importlib
    import pkgutil

    from fastapi import APIRouter

    import src.infrastructure.rest.routers as routers_pkg

    paths: set[str] = set()
    # `walk_packages`, not `iter_modules`: the routers are grouped into a package per served
    # surface, and a flat scan sees the packages without ever importing the modules inside them —
    # which reads as "no such endpoint" for every route in them.
    for module_info in pkgutil.walk_packages(routers_pkg.__path__, f"{routers_pkg.__name__}."):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, APIRouter):
                paths |= {
                    path for path in
                    (getattr(route, "path", "") for route in value.routes) if path
                }
    return paths


def _path_matches(documented: str, registered: set[str]) -> bool:
    """A documented path matches a registered one, treating `{param}` segments as
    wildcards so `/api/assurance/nodes/{node_id}` and a doc's `/api/.../{id}`
    agree."""
    if documented in registered:
        return True
    doc_parts = documented.strip("/").split("/")
    for candidate in registered:
        cand_parts = candidate.strip("/").split("/")
        if len(cand_parts) != len(doc_parts):
            continue
        if all(
            c == d or (c.startswith("{") and c.endswith("}"))
            or (d.startswith("{") and d.endswith("}"))
            for c, d in zip(cand_parts, doc_parts)
        ):
            return True
    return False


def _documented_paths(text: str) -> set[str]:
    """Every `/api/...` path in a code span, including `POST /api/...` forms.

    Anchored on the OPENING backtick and allowing an optional method, rather than
    matching balanced spans: fenced code blocks (```) break backtick pairing, and
    a pairing-based extractor silently dropped 7 of 10 documented paths — a check
    that passes because it found nothing is worse than no check.
    """
    return set(re.findall(r"`(?:[A-Z]+\s+)?(/api/[A-Za-z0-9/_{}-]+)", text))


def test_documented_api_endpoints_are_registered_routes() -> None:
    registered = _registered_paths()
    assert registered, "no routes discovered — the check would pass vacuously"

    offenders: list[str] = []
    for path, text in _docs_text().items():
        for documented in sorted(_documented_paths(text)):
            if not _path_matches(documented, registered):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {documented}")

    assert offenders == [], (
        "Documentation names HTTP endpoints that are not registered:\n  "
        + "\n  ".join(offenders)
    )


# ── CLI subcommands ───────────────────────────────────────────────────────────

#: Console scripts whose subcommands are documented and therefore checkable.
_SUBCOMMAND_CLIS = ("arch-assurance",)


def _real_subcommands(command: str) -> set[str]:
    completed = subprocess.run(
        ["uv", "run", command, "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=180,
    )
    match = re.search(r"\{([a-z0-9,\-]+)\}", completed.stdout)
    return set(match.group(1).split(",")) if match else set()


@pytest.mark.parametrize("command", _SUBCOMMAND_CLIS)
def test_documented_cli_subcommands_exist(command: str) -> None:
    real = _real_subcommands(command)
    assert real, f"could not enumerate {command} subcommands — check would pass vacuously"

    offenders: list[str] = []
    for path, text in _docs_text().items():
        for named in sorted(set(re.findall(rf"{re.escape(command)} ([a-z][a-z0-9-]*)", text))):
            # Long-form flags and prose words are not subcommands.
            if named.startswith("-"):
                continue
            if named not in real:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {command} {named}")

    assert offenders == [], (
        f"Documentation names {command} subcommands that do not exist:\n  "
        + "\n  ".join(offenders)
        + f"\nReal subcommands: {', '.join(sorted(real))}"
    )


# ── MCP tools ─────────────────────────────────────────────────────────────────


def _registered_tool_names() -> set[str]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
    from src.infrastructure.mcp.mcp_assurance_server import (
        mcp_assurance_read,
        mcp_assurance_write,
    )

    names: set[str] = set()
    for server in (mcp_read, mcp_write, mcp_assurance_read, mcp_assurance_write):
        names |= {t.name for t in server._tool_manager.list_tools()}  # noqa: SLF001
    return names


#: Identifiers that share the tool-name shape but denote something else. Each one
#: is listed deliberately: an unexplained exclusion here would quietly re-open the
#: gap this test exists to close.
_NON_TOOL_IDENTIFIERS = {
    "assurance_analyses": "database table",
    "assurance_store_locked": "error envelope code",
    "artifact_write": "application layer",
    "artifact_type": "record/REST field name",
}


def test_documented_mcp_tool_names_are_registered() -> None:
    registered = _registered_tool_names()
    assert registered, "no MCP tools discovered — the check would pass vacuously"

    offenders: list[str] = []
    for path, text in _docs_text().items():
        for named in sorted(set(re.findall(r"`((?:assurance|artifact)_[a-z_]+)`", text))):
            if named in _NON_TOOL_IDENTIFIERS:
                continue
            if named not in registered:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {named}")

    assert offenders == [], (
        "Documentation names MCP tools that are not registered:\n  "
        + "\n  ".join(offenders)
    )


# ── The assurance capability inventory ────────────────────────────────────────

_CAPABILITY_DOC = DOCS / "architecture" / "assurance-gui-capability-design.md"


def _inventory_http_tokens() -> list[tuple[str, str]]:
    """(capability, http token) for every non-empty HTTP cell of the inventory."""
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in _CAPABILITY_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Capability |"):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            break
        if not in_table or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        capability, http = cells[0], cells[4]
        if http in ("", "—", "-"):
            continue
        rows.extend((capability, token.strip()) for token in http.split(",") if token.strip())
    return rows


def test_capability_inventory_names_real_endpoints() -> None:
    """The inventory's HTTP column drifted for a month, still advertising adapters
    deleted with the legacy connectors. Each token must be the final segment of a
    registered assurance route, so a removed endpoint fails here instead of being
    discovered by a reader."""
    tokens = _inventory_http_tokens()
    assert tokens, "no HTTP cells parsed from the capability inventory"

    segments = {
        path.rsplit("/", 1)[-1]
        for path in _registered_paths()
        if path.startswith("/api/assurance/")
    }
    offenders = [
        f"{capability!r} names {token!r}" for capability, token in tokens
        if token not in segments
    ]

    assert offenders == [], (
        "The assurance capability inventory names HTTP surfaces that no longer exist:\n  "
        + "\n  ".join(offenders)
        + "\nUpdate docs/architecture/assurance-gui-capability-design.md when a surface changes."
    )


# ── Repository paths ──────────────────────────────────────────────────────────

#: Documented paths that legitimately do not exist in a checkout. Kept explicit:
#: an unexplained entry would hide a genuinely dead reference.
_UNCOMMITTED_PATHS = {
    "tools/plantuml.jar": "downloaded at first render, not committed",
    "plantuml.jar": "downloaded by get-plantuml beside pyproject.toml, not committed",
    "tools/gui/dist/": "SPA build output produced by `npm run build`, gitignored",
}


def test_documented_repository_paths_exist() -> None:
    """A doc pointing at a moved or deleted file is a dead reference that no
    reader can act on, and nothing else in the build notices it."""
    offenders: list[str] = []
    for path, text in _docs_text().items():
        for named in sorted(set(re.findall(
            r"`((?:src|tools|docs|engagements)/[A-Za-z0-9/_.@-]+)`", text,
        ))):
            if named in _UNCOMMITTED_PATHS:
                continue
            if not (REPO_ROOT / named).exists():
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {named}")

    assert offenders == [], (
        "Documentation points at repository paths that do not exist:\n  "
        + "\n  ".join(offenders)
    )


# ── Vocabularies duplicated in a client ───────────────────────────────────────

_WIZARD_HELPERS = (
    REPO_ROOT / "tools" / "gui" / "src" / "ui" / "views"
    / "AssuranceSupplyChainWizard.helpers.ts"
)


def test_frontend_anchor_types_match_the_backend_vocabulary() -> None:
    """The scope picker needs the admissible anchor types synchronously, so it
    keeps a client copy of a vocabulary the BACKEND owns. A copy that can drift is
    how a GUI comes to offer an ingest the API refuses — this pins the two
    together so the duplication is safe rather than merely convenient."""
    from src.domain.assurance.security_signal_snapshot import ADMISSIBLE_ANCHOR_TYPES

    source = _WIZARD_HELPERS.read_text(encoding="utf-8")
    block = re.search(
        r"ADMISSIBLE_ANCHOR_TYPES\s*=\s*\[(.*?)\]", source, re.S,
    )
    assert block, "could not locate ADMISSIBLE_ANCHOR_TYPES in the wizard helpers"
    frontend = tuple(re.findall(r"'([a-z-]+)'", block.group(1)))

    assert frontend == tuple(ADMISSIBLE_ANCHOR_TYPES), (
        "The GUI's admissible anchor types have drifted from the backend's:\n"
        f"  frontend: {frontend}\n"
        f"  backend:  {tuple(ADMISSIBLE_ANCHOR_TYPES)}\n"
        "The backend owns this vocabulary; update the client copy."
    )
