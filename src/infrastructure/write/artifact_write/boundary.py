from collections.abc import Sequence
from pathlib import Path

from src.config.workspace_paths import infer_repo_scope
from src.domain.clock import utc_now_iso


def modification_stamp() -> str:
    """The `last-updated` value a write path stamps: a full UTC ISO-8601 datetime
    (`YYYY-MM-DDTHH:MM:SSZ`) from the central clock, so modification order is
    resolvable to the second and consistent with the assurance store's timestamps."""
    return utc_now_iso()


def normalize_specializations(
    specialization: str | None, specializations: Sequence[str] | None
) -> tuple[str, ...]:
    """The applied-specialization set a write path should use, from its two inputs.

    ``specializations`` (the list, from a multi-select client) wins when given; otherwise
    the single ``specialization`` scalar is lifted to a one-element set (every existing
    caller and the single-value REST/MCP field). Order preserved, blanks and duplicates
    dropped. A concept may carry several (ArchiMate §15.2)."""
    raw = list(specializations) if specializations else ([specialization] if specialization else [])
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
