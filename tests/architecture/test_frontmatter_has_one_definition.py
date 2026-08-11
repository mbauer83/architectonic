"""What counts as a frontmatter block is decided in one module, and nowhere else.

It used to be decided in **fourteen** places, in five families that did not agree — a strict reading
that required a newline after the closing fence, a MULTILINE one, a whitespace-tolerant one, an
imperative `find("\\n---\\n")`, and a loose `startswith("---")` plus `find("\\n---", 3)` that accepted
`----` and `---anything` as an opening fence. The two loosest were the *verifier* and the document write
path, so a file could be verified under one delimitation and rewritten under another.

Measured before unifying: across 975 files in both repositories the five readings disagreed on zero, so
the divergence had not yet produced a wrong answer. That is the reason to close it now rather than the
reason not to — the next hand-edited file is where it would have surfaced, and it would have surfaced as
one tool seeing frontmatter another did not.

**Scope: readers.** A first attempt at this test scanned every string literal for three dashes and
reported seventeen files — markdown table separators, the artifact-id `---` separator, an error message
that quotes the fence in prose, and the three writers that legitimately *compose* frontmatter. Breadth
was the wrong instrument: what matters is not mentioning a fence but *deciding where one is*. So this
inspects the call, not the literal. Composing output is left alone; if that accretes, it is its own item.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources

#: The module that owns the delimitation.
_OWNER = Path("src/domain/repository/frontmatter.py")

#: Three dashes against a line boundary, in a regex handed to `re`. Both spellings of a boundary count:
#: a real newline (from `"---\n"`) and the two characters `\` `n` (from a raw `r"^---\n"`), plus the regex
#: anchors `^ $ \A \Z` as literal text. There is deliberately no bare start-of-string alternative — with
#: one, every literal *beginning* `---` matched, which reported `artifact_id.split("---")`: the connection
#: id separator, not a fence.
_ANCHORED_FENCE = re.compile(r"(?:\n|\\n|\\A|\^|\\r)-{3}|-{3}(?:\n|\\n|\\r|\\Z|\$|\[ \\t\])")

#: Calls that locate a fence, whether by substring or by pattern. One set, because both take the same
#: evidence: the literal must carry a line boundary. `find("---")` and `split("---")` without one are the
#: connection-id separator in `source---target@@type`, which two modules legitimately look for.
_LOCATING_CALLS = frozenset({
    "find", "index", "rfind", "partition", "removeprefix",
    "match", "fullmatch", "search", "sub", "subn", "compile", "split",
})


def _first_string_argument(call: ast.Call) -> str | None:
    for argument in call.args:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument.value
        break
    return None


def _called_name(call: ast.Call) -> str:
    target = call.func
    if isinstance(target, ast.Attribute):
        return target.attr
    return target.id if isinstance(target, ast.Name) else ""


def _fence_decision(call: ast.Call) -> str | None:
    """The fence literal this call decides on, or None if it is not deciding where a fence is."""
    literal = _first_string_argument(call)
    if literal is None:
        return None
    name = _called_name(call)
    # `startswith` is its own rule: a bare `"---"` prefix check *is* the loose guard this replaced, and
    # needs no boundary in the literal because the string position supplies it.
    if name == "startswith" and literal.startswith("---"):
        return literal
    if name in _LOCATING_CALLS and _ANCHORED_FENCE.search(literal):
        return literal
    return None


def _hand_rolled_fence_readings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        {found for node in ast.walk(tree) if isinstance(node, ast.Call) and (found := _fence_decision(node))}
    )


def _offenders() -> dict[str, list[str]]:
    return {
        str(path.relative_to(REPO_ROOT)): found
        for path in python_sources(SRC, TOOLS)
        if path.relative_to(REPO_ROOT) != _OWNER and (found := _hand_rolled_fence_readings(path))
    }


def test_the_owner_module_exists_where_this_test_expects_it() -> None:
    # Without this, moving the module would make the assertion below vacuously true.
    assert (REPO_ROOT / _OWNER).is_file(), f"{_OWNER} is the single owner and it is not there"


def test_nothing_outside_the_owner_spells_a_frontmatter_fence() -> None:
    offenders = _offenders()

    assert offenders == {}, (
        "these spell the frontmatter fence themselves, which is how fourteen readings of one rule "
        "accumulated. Use `src.domain.repository.frontmatter`: `read_frontmatter` for the block, "
        "`parse_frontmatter` for the mapping, `body_after_frontmatter` to strip it, "
        "`replace_frontmatter_text` to rewrite it, `opens_with_frontmatter` for the cheap guard. "
        f"{offenders}"
    )


def _decides(code: str) -> list[str]:
    """The fence decisions in a snippet — the guard applied to source, as it is in the walk."""
    tree = ast.parse(code)
    return sorted(
        {found for node in ast.walk(tree) if isinstance(node, ast.Call) and (found := _fence_decision(node))}
    )


@pytest.mark.parametrize(
    "reading",
    [
        pytest.param('re.match(r"^---\\n(.*?\\n)---\\n", text, re.DOTALL)', id="strict-capture"),
        pytest.param('re.compile(r"^---\\n(.*?)^---\\n", re.MULTILINE | re.DOTALL)', id="multiline"),
        pytest.param('re.compile(r"^---\\n(.*?)\\n---\\s*\\n?", re.DOTALL)', id="whitespace-tolerant"),
        pytest.param('re.compile(r"^---\\n.*?\\n---\\n", re.DOTALL)', id="strip-only"),
        pytest.param('re.compile(r"^(---\\n)(.*?)(\\n---\\n)", re.DOTALL)', id="three-group-rewriter"),
        pytest.param('re.compile(r"\\A---[ \\t]*\\r?\\n.*?\\r?\\n---[ \\t]*(?:\\r?\\n|$)", re.DOTALL)', id="puml"),
        pytest.param('content.startswith("---")', id="loose-guard"),
        pytest.param('content.startswith("---\\n")', id="fenced-guard"),
        pytest.param('content.find("\\n---", 3)', id="loose-locator"),
        pytest.param('content.find("\\n---\\n", 4)', id="fenced-locator"),
    ],
)
def test_it_recognises_each_reading_this_replaced(reading: str) -> None:
    """Every case below was in the codebase. A spelling the guard misses is one that can come back."""
    assert _decides(reading) != [], reading


@pytest.mark.parametrize(
    "innocent",
    [
        pytest.param('line.startswith("|---")', id="markdown-table-separator"),
        pytest.param('artifact_id.split("---")', id="connection-id-separator"),
        pytest.param('start = endpoints_part.find("---")', id="connection-id-separator-located"),
        pytest.param('dash = conn_id.find("---")', id="connection-id-separator-in-verifier"),
        pytest.param('Issue(Severity.ERROR, "E012", "Frontmatter opening --- has no closing ---", loc)', id="prose"),
        pytest.param('lines.append("\' --- Auto-layout: spread elements ---")', id="puml-comment"),
        pytest.param('parts.append("-" * 8)', id="rule-of-dashes"),
        pytest.param('text.startswith("--verbose")', id="cli-flag"),
        pytest.param('body = f"---\\n{dumped}\\n---\\n{rest}"', id="composing-output"),
    ],
)
def test_it_leaves_ordinary_code_alone(innocent: str) -> None:
    """A guard that cries wolf gets suppressed, so what it must *not* flag is pinned too.

    The last case is the important one: composing frontmatter is not deciding where one is, and three
    writers legitimately do it.
    """
    assert _decides(innocent) == [], innocent


def test_the_scan_sees_the_files_it_means_to() -> None:
    files = list(python_sources(SRC, TOOLS))
    assert len(files) > 500, len(files)
    relative = {str(p.relative_to(REPO_ROOT)) for p in files}
    assert str(_OWNER) in relative
    # The file that held the loosest of the fourteen readings, so the scan provably covers it.
    assert "src/application/verification/artifact_verifier_parsing.py" in relative
