"""Per-diagram edge-label override editing.

Split out of ``diagram_edit.py`` to keep that module's much larger
field-merging function within the LoC policy — this is a small, self-contained
wrapper around ``edit_diagram``.
"""

from collections.abc import Callable
from pathlib import Path

from src.application.repo_path_helpers import diagram_source_root, resolve_diagram_source_path
from src.application.verification.artifact_verifier import ArtifactVerifier

from .parse_existing import parse_diagram_file
from .types import WriteResult


def set_diagram_edge_label(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    edge_key: str,
    label: str | None,
    dry_run: bool,
) -> WriteResult:
    """Set or clear a per-diagram edge-label override for a single edge.

    ``edge_key`` is ``"{src_alias}:{tgt_alias}"`` from the rendered PUML.
    ``label=None`` removes the override, reverting to the derived label.
    """
    from .diagram_edit import edit_diagram  # noqa: PLC0415

    _find = verifier.registry.find_file_by_id if verifier.registry is not None else None
    diagram_path = resolve_diagram_source_path(repo_root, artifact_id, _find)
    if diagram_path is None:
        raise ValueError(f"Diagram '{artifact_id}' not found under {diagram_source_root(repo_root)}")

    parsed = parse_diagram_file(diagram_path)
    raw_el = parsed.frontmatter.get("edge-labels")
    current: dict[str, str | None] = dict(raw_el) if isinstance(raw_el, dict) else {}

    if label is None:
        current.pop(edge_key, None)
    else:
        current[edge_key] = label

    return edit_diagram(
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        edge_labels=current,
        dry_run=dry_run,
    )
