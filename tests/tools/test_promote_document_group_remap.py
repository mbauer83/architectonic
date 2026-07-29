"""Group-remapped promotion of documents: the copied file must land in the REMAPPED
docs/<type>/<group>/ directory and its relative references into remapped
`projects/<slug>/` directories must be rewritten — otherwise a promoted standard's
required entity links break exactly when its linked entities move groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.infrastructure.write.artifact_write._promote_file_ops import _remap_grouped_rel, copy_simple


@dataclass
class _Result:
    copied_files: list[str] = field(default_factory=list)
    verification_errors: list[str] = field(default_factory=list)


@dataclass
class _Registry:
    file: Path

    def find_file_by_id(self, aid: str) -> Path | None:
        return self.file


def test_remap_grouped_rel_rewrites_docs_and_diagram_group_dirs() -> None:
    remap = {"platform-core": "engineering-quality"}
    assert _remap_grouped_rel(Path("docs/standard/platform-core/x.md"), remap) == Path(
        "docs/standard/engineering-quality/x.md"
    )
    assert _remap_grouped_rel(Path("diagram-catalog/diagrams/platform-core/x.puml"), remap) == Path(
        "diagram-catalog/diagrams/engineering-quality/x.puml"
    )
    assert _remap_grouped_rel(Path("docs/standard/other/x.md"), remap) == Path("docs/standard/other/x.md")


def test_copy_simple_remaps_group_dir_and_rewrites_project_hrefs(tmp_path: Path) -> None:
    eng_root = tmp_path / "engagement"
    ent_root = tmp_path / "enterprise"
    doc = eng_root / "docs" / "standard" / "platform-core" / "STD@1.Abc123.sample.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "See [Req](../../../projects/motivation-narrative/model/motivation/requirement/REQ@1.Xyz789.req.md)\n",
        encoding="utf-8",
    )
    result = _Result()

    copy_simple(
        "STD@1.Abc123.sample",
        eng_root,
        ent_root,
        _Registry(doc),
        result,
        [],
        [],
        {"platform-core": "engineering-quality", "motivation-narrative": "engineering-quality"},
    )

    dest = ent_root / "docs" / "standard" / "engineering-quality" / "STD@1.Abc123.sample.md"
    assert dest.exists()
    assert "projects/engineering-quality/model/motivation/requirement/REQ@1.Xyz789.req.md" in dest.read_text()
    assert "projects/motivation-narrative/" not in dest.read_text()
    assert result.copied_files == ["docs/standard/engineering-quality/STD@1.Abc123.sample.md"]


def test_copy_simple_without_remap_copies_verbatim(tmp_path: Path) -> None:
    eng_root = tmp_path / "engagement"
    ent_root = tmp_path / "enterprise"
    doc = eng_root / "docs" / "standard" / "platform-core" / "STD@1.Abc123.sample.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("See [Req](../../../projects/motivation-narrative/model/x.md)\n", encoding="utf-8")
    result = _Result()

    copy_simple("STD@1.Abc123.sample", eng_root, ent_root, _Registry(doc), result, [], [])

    dest = ent_root / "docs" / "standard" / "platform-core" / "STD@1.Abc123.sample.md"
    assert dest.exists()
    assert dest.read_text() == doc.read_text()
