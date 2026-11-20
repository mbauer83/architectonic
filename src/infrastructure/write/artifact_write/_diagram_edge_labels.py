"""Per-diagram edge-label override editing.

Split out of ``diagram_edit.py`` to keep that module's much larger
field-merging function within the LoC policy — this is a small, self-contained
wrapper around ``edit_diagram``.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.diagrams.relation_key import read_relation_key

from .boundary import assert_engagement_write_root
from .types import WriteResult


def merged_edge_labels(
    stored: object, changes: Mapping[str, str | None] | None
) -> dict[str, str] | None:
    """The labels a diagram states after *changes*: a value sets its key, None removes it.

    Every key is held in the canonical spelling of the drawn relation it names, so a label stated
    under a slugged connection id and one stated under its stable form are one statement. A key in
    the retired alias-pair form is refused, with what to run.
    """
    merged = {
        read_relation_key(str(key)).text: str(label)
        for key, label in (stored.items() if isinstance(stored, Mapping) else ())
    }
    for key, label in (changes or {}).items():
        canonical = read_relation_key(key).text
        if label is None:
            merged.pop(canonical, None)
        else:
            merged[canonical] = label
    return merged or None


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

    ``edge_key`` is the drawn relation's key (`src.domain.diagrams.relation_key`): the connection
    id, qualified by the instances at its ends where either is a further occurrence.
    ``label=None`` removes the override, reverting to the derived label.
    """
    from .diagram_edit import edit_diagram  # noqa: PLC0415

    return edit_diagram(
        assert_write_root=assert_engagement_write_root,
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        edge_labels={edge_key: label},
        dry_run=dry_run,
    )
