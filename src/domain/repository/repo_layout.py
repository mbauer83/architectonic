"""Canonical directory-name constants for the architecture repository structure.

Import these instead of bare string literals so that a directory rename is a
one-line change rather than a grep-and-replace across the entire codebase.
"""

ENGAGEMENT_REPO = "architecture-repository"
MODEL = "model"
DOCS = "docs"
PROJECTS = "projects"  # model-project group containers: PROJECTS/<slug>/MODEL/...
DIAGRAM_CATALOG = "diagram-catalog"
DIAGRAMS = "diagrams"  # subdirectory within DIAGRAM_CATALOG/
RENDERED = "rendered"  # subdirectory within DIAGRAM_CATALOG/ — derived output, excluded from indexing
RENDERED_SUFFIXES: tuple[str, ...] = (".png", ".svg")
MANAGED_INCLUDE_BASENAMES = frozenset({
    "_archimate-stereotypes.puml",
    "_archimate-glyphs.puml",
    "_archimate-relations.puml",
    "_macros.puml",
})

ICONS = "icons"  # subdirectory within DIAGRAM_CATALOG/ — the shared icon library, ICO@….md
ARCH_REPO = ".arch-repo"
ARCH_DOC_SCHEMATA = "documents"  # subdirectory within ARCH_REPO/ — document type JSON schemas
SCRATCHPADS = "scratchpads"  # SCRATCHPADS/<group-slug>/SCR@….scratchpad.yaml — free-standing
#: Two dots so the kind is readable in a directory listing, and so a glob for scratchpads cannot
#: also match a stray `.yaml` someone dropped beside them. Here rather than on the repository
#: because it is a fact about the layout, and the index scans for it without owning the writing.
SCRATCHPAD_SUFFIX = ".scratchpad.yaml"
#: The file beside an entity's own that declares its outgoing connections.
OUTGOING_SUFFIX = ".outgoing.md"
#: The file extensions an artifact's source may carry. Entities, connections and documents are
#: markdown; a diagram is `.puml` unless its notation *is* markdown, which the matrix type's is.
#: Stated once because a reader that spells only `.md` sees no diagram at all — which is what kept
#: a document's link to a PlantUML diagram from satisfying a `diagram:` reference term.
ARTIFACT_SOURCE_SUFFIXES: frozenset[str] = frozenset({".md", ".puml"})

#: Where a transaction keeps its journal and staging trees, and where a pull keeps its worktrees —
#: both inside `ARCH_REPO/`, beside the configuration, and neither is configuration.
TRANSACTIONS = "transactions"
SYNC_WORKTREES = "sync-worktrees"
EXCHANGE_IDENTITY = "exchange-identity.json"
#: The deployment's own state directory: sync state, the backend log, upgrade checkpoints.
RUNTIME_STATE_DIR = ".arch"

#: **What in a repository is not repository content.** Everything else under the root is: git covers
#: the whole repository except what is named here, so a directory the layout gains later is content
#: the day it appears, with nothing to remember.
#:
#: Declared once because it was spelled five times and the spellings disagreed. Three of them named
#: what *is* content instead — `model/`, `docs/`, `diagram-catalog/` — and so predated both
#: `projects/` and `scratchpads/`: a pull moved the branch and left a grouped entity at its old
#: content, which the next save then published as a reversal of a teammate's work, while the status
#: reported nothing to save for the same directories. A list of exceptions cannot fall behind the
#: layout that way; a list of members always will.
#:
#: Paths relative to the repository root; a trailing `/` marks a directory, everything beneath which
#: is runtime state. Stated as plain paths rather than in any tool's pattern dialect, because two
#: dialects are derived from it — git's pathspecs and `.gitignore` lines — and neither should have
#: to be parsed back out of the other.
RUNTIME_STATE: tuple[str, ...] = (
    f"{RUNTIME_STATE_DIR}/",
    f"{ARCH_REPO}/{TRANSACTIONS}/",
    f"{ARCH_REPO}/{SYNC_WORKTREES}/",
    f"{ARCH_REPO}/{EXCHANGE_IDENTITY}",
)


def is_runtime_path(relative: str) -> bool:
    """Whether a root-relative path belongs to Git or to the product's local state."""
    return relative == ".git" or relative.startswith(".git/") or any(
        relative == entry.rstrip("/") or (entry.endswith("/") and relative.startswith(entry))
        for entry in RUNTIME_STATE
    )


def is_configuration_path(relative: str) -> bool:
    return "/" not in relative or relative.startswith(f"{ARCH_REPO}/")
