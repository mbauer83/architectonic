"""The documented update of an installation without `.git` removes what a release renamed away.

The procedure is read from `docs/reference/software-update.md` (the block after its
`<!-- tested: overlay-update -->` marker) and run as written, with its four variables pointed at
fixture repositories. Regression: the procedure listed removals with `--diff-filter=D` alone, which
reports a renamed file as a rename, so the old path survived as a stale, importable file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[2] / "docs" / "reference" / "software-update.md"
_MARKER = "<!-- tested: overlay-update"


def _documented_block() -> str:
    text = DOC.read_text(encoding="utf-8")
    after = text[text.index(_MARKER):]
    match = re.search(r"```bash\n(.*?)```", after, re.DOTALL)
    assert match is not None, "the tested block must follow its marker"
    return match.group(1)


def _run_with(block: str, **variables: str) -> subprocess.CompletedProcess[str]:
    """The block with its variable assignments replaced by `variables`, run by bash."""
    for name, value in variables.items():
        block, count = re.subn(rf"^{name}=\S+", f"{name}={value}", block, flags=re.MULTILINE)
        assert count == 1, f"the block assigns {name} once"
    return subprocess.run(["bash", "-euo", "pipefail", "-c", block], capture_output=True, text=True, check=True)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _write(root: Path, relative: str, content: str = "x\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def releases(tmp_path: Path) -> tuple[Path, Path]:
    """A clone with two tagged releases, and an installation of the first kept without `.git`.

    v2 renames `pkg/old_name.py` to `pkg/new_name.py`, deletes `pkg/gone.py` and adds an ignore rule.
    The installation also holds an ignored environment, a file a previous overlay left behind, and a
    file v2 newly ignores.
    """
    src = tmp_path / "clone"
    src.mkdir()
    _git(src, "init", "-q", "-b", "main")
    _git(src, "config", "user.email", "fixture@example.invalid")
    _git(src, "config", "user.name", "Fixture")
    _write(src, ".gitignore", ".venv/\n")
    _write(src, "pkg/old_name.py", "def f():\n    return 1\n")
    _write(src, "pkg/gone.py")
    _write(src, "pkg/kept.py")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "v1")
    _git(src, "tag", "v1")
    _git(src, "mv", "pkg/old_name.py", "pkg/new_name.py")
    _git(src, "rm", "-q", "pkg/gone.py")
    _write(src, ".gitignore", ".venv/\nlocal-notes/\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "v2")
    _git(src, "tag", "v2")

    tree = tmp_path / "installation"
    tree.mkdir()
    archive = subprocess.run(["git", "archive", "v1"], cwd=src, check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
    _write(tree, ".venv/lib/site.py")
    _write(tree, "pkg/stale_from_an_earlier_overlay.py")
    _write(tree, "local-notes/todo.md")
    return src, tree


def test_the_documented_procedure_converges_the_tree_on_the_new_release(releases: tuple[Path, Path]) -> None:
    src, tree = releases
    result = _run_with(_documented_block(), SRC=str(src), OLD="v1", NEW="v2", TREE=str(tree))

    assert not (tree / "pkg/old_name.py").exists(), "a path renamed away is removed"
    assert not (tree / "pkg/gone.py").exists()
    assert (tree / "pkg/new_name.py").exists()
    assert (tree / "pkg/kept.py").exists()
    assert (tree / ".venv/lib/site.py").exists(), "what the release ignores is left alone"
    assert (tree / "local-notes/todo.md").exists()
    assert result.stdout.split() == ["pkg/stale_from_an_earlier_overlay.py"]
    assert (tree / "pkg/stale_from_an_earlier_overlay.py").exists(), "listing changes nothing"


def test_without_no_renames_the_renamed_path_survives(releases: tuple[Path, Path]) -> None:
    """The procedure as it was: why `--no-renames` is in the block."""
    src, tree = releases
    block = _documented_block().replace("--no-renames ", "")
    _run_with(block, SRC=str(src), OLD="v1", NEW="v2", TREE=str(tree))
    assert (tree / "pkg/old_name.py").exists()
