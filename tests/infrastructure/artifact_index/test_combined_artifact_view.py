from __future__ import annotations

from pathlib import Path

from src.infrastructure.artifact_index import combined_artifact_index, shared_artifact_index


def _write_entity(path: Path, artifact_id: str, name: str, artifact_type: str = "goal") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {artifact_id}\n"
        f"artifact-type: {artifact_type}\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"## {name}\n\nshared search text\n",
        encoding="utf-8",
    )


def test_combined_view_reuses_single_root_indexes(tmp_path: Path) -> None:
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    engagement.mkdir(parents=True)
    enterprise.mkdir()

    combined = combined_artifact_index(engagement, enterprise)

    assert shared_artifact_index([engagement, enterprise]) is combined
    assert combined._engagement is shared_artifact_index(engagement)  # noqa: SLF001
    assert combined._enterprise is shared_artifact_index(enterprise)  # noqa: SLF001


def test_combined_view_preserves_sorted_lists_and_scope_filters(tmp_path: Path) -> None:
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    _write_entity(engagement / "model" / "motivation" / "goal" / "GOL@2.zzz.zzz.md", "GOL@2.zzz.zzz", "Shared")
    _write_entity(enterprise / "model" / "motivation" / "goal" / "GOL@1.aaa.aaa.md", "GOL@1.aaa.aaa", "Shared")

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    assert [entity.artifact_id for entity in combined.list_entities()] == [
        "GOL@1.aaa.aaa",
        "GOL@2.zzz.zzz",
    ]
    assert [entity.artifact_id for entity in combined.find_entities_by_name("Shared", scope="engagement")] == [
        "GOL@2.zzz.zzz",
    ]
    assert [entity.artifact_id for entity in combined.find_entities_by_name("Shared", scope="enterprise")] == [
        "GOL@1.aaa.aaa",
    ]


def test_combined_search_keeps_limit_per_record_type(tmp_path: Path) -> None:
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    _write_entity(
        engagement / "model" / "motivation" / "goal" / "GOL@3.eng.eng.md",
        "GOL@3.eng.eng",
        "Alpha",
    )
    _write_entity(
        enterprise / "model" / "motivation" / "goal" / "GOL@4.ent.ent.md",
        "GOL@4.ent.ent",
        "Alpha",
    )
    doc = enterprise / "docs" / "ADR@5.doc.doc.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "---\n"
        "artifact-id: ADR@5.doc.doc\n"
        "artifact-type: document\n"
        "doc-type: adr\n"
        "title: Alpha Decision\n"
        "status: draft\n"
        "---\n\n"
        "Alpha\n",
        encoding="utf-8",
    )

    combined = combined_artifact_index(engagement, enterprise)
    combined.refresh()

    rows = combined.search_fts("Alpha", limit=1, include_connections=False, include_diagrams=False)
    assert [row[1] for row in rows].count("entity") == 1
    assert [row[1] for row in rows].count("document") == 1
