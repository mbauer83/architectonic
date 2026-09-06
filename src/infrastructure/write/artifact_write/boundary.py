from collections.abc import Sequence
from pathlib import Path

from src.config.workspace_paths import infer_repo_scope
from src.domain.clock import utc_now_iso


def modification_stamp() -> str:
    """The `last-updated` value a write path stamps: a full UTC ISO-8601 datetime
    (`YYYY-MM-DDTHH:MM:SSZ`) from the central clock, so modification order is
    resolvable to the second and consistent with the assurance store's timestamps."""
    return utc_now_iso()


def normalize_specializations(specializations: Sequence[str] | None) -> tuple[str, ...]:
    """The applied-specialization set a write path should use.

    Order preserved, blanks and duplicates dropped. A concept may carry several
    (ArchiMate §15.2), and this is the only shape a write path accepts — the scalar it also
    took was a second way to say the one-element case, which every layer above had to thread
    and every layer could disagree about."""
    raw = list(specializations) if specializations else []
    seen: dict[str, None] = {}
    for item in raw:
        if item and item not in seen:
            seen[item] = None
    return tuple(seen)


def assert_engagement_write_root(repo_root: Path) -> None:
    """Reject writes to the enterprise repository root.

    This guard is called unconditionally by all standard MCP write tools and
    normal GUI write endpoints.  It is intentionally not bypassable via any
    argument — admin-mode GUI writes use a separate code path that calls
    assert_enterprise_write_root instead.
    """
    p = repo_root.resolve()
    if infer_repo_scope(p) == "enterprise":
        raise ValueError("Refusing to write to enterprise repository. Point repo_root at an engagement repository.")


def owned_by(path: Path, repo_root: Path) -> bool:
    """Whether `repo_root` is the repository this file belongs to, and so may write it.

    **The question `assert_engagement_write_root` does not ask.** That one checks the *root* a write
    was handed; this checks the *file* it is about to touch. The registry a write path is given spans
    both tiers, so an artifact addressed by its enterprise id resolves to an enterprise file while
    the root argument is still the engagement's — the guard passes and the write lands upstream.

    Spelled twice before this existed, in the entity delete and the bulk delete preflight, and absent
    from every edit. That absence is what let a PATCH to an enterprise artifact's own id modify the
    enterprise repository from an engagement deployment.
    """
    # Compared as given, not resolved. Both come from the same configuration — the write root and
    # the index's own paths — so they share a prefix form, and resolving one side through a symlink
    # made a repository disown files it had just written. That was this extraction adding a change
    # nobody asked for; the two callers it came from compared them exactly like this.
    try:
        path.relative_to(repo_root)
    except ValueError:
        return False
    return True


def assert_owned_by(path: Path, repo_root: Path, *, artifact_id: str) -> None:
    """Refuse a write to a file the repository being written does not own."""
    if not owned_by(path, repo_root):
        raise ValueError(f"Entity '{artifact_id}' is not in writable repo '{repo_root}'")


def assert_enterprise_write_root(repo_root: Path) -> None:
    """Accept only the enterprise repository root — for admin-mode GUI writes."""
    p = repo_root.resolve()
    if infer_repo_scope(p) != "enterprise":
        raise ValueError(f"Admin write expected enterprise repository root, got: {p}")


def engagement_id_from_repo_root(repo_root: Path) -> str:
    # engagements/<id>/work-repositories/<repo>/
    parts = repo_root.resolve().parts
    if "engagements" in parts:
        idx = parts.index("engagements")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "ENG-UNKNOWN"
