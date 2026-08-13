"""The one YAML loader: what it parses, what it raises, and that it is the fast one.

`parse_yaml` replaced 77 direct `yaml.safe_load` calls, so two properties carry the whole change. It
must accept and return what `safe_load` did — otherwise 63 files changed meaning, not just speed — and
it must raise `yaml.YAMLError`, because ~15 call sites catch exactly that and a different exception type
would turn a handled malformed file into a crash.

The equivalence check at the end reads the real repository. It asserts an invariant — no document parses
differently under the two loaders — never a document count, so authoring content cannot fail it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.domain.yaml_documents import USES_LIBYAML, parse_yaml
from src.infrastructure.rendering.puml_runtime import is_render_scratch

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestWhatItParses:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param("a: 1\nb: two\n", {"a": 1, "b": "two"}, id="mapping"),
            pytest.param("- 1\n- 2\n", [1, 2], id="sequence"),
            pytest.param("just a string\n", "just a string", id="scalar"),
            pytest.param("", None, id="empty-document"),
            pytest.param("~\n", None, id="explicit-null"),
            pytest.param("d: 2026-08-11\n", {"d": date(2026, 8, 11)}, id="date"),
            pytest.param("n: 0755\n", {"n": 493}, id="octal"),
            pytest.param('s: "café 😀"\n', {"s": "café 😀"}, id="unicode"),
            pytest.param(
                "base: &b {x: 1}\nd: {<<: *b, y: 2}\n",
                {"base": {"x": 1}, "d": {"x": 1, "y": 2}},
                id="merge-key",
            ),
        ],
    )
    def test_it_returns_what_the_document_says(self, text: str, expected: object) -> None:
        assert parse_yaml(text) == expected

    def test_it_accepts_an_open_file(self, tmp_path: Path) -> None:
        """Several call sites hand it a handle rather than text, as `safe_load` allowed."""
        path = tmp_path / "doc.yaml"
        path.write_text("a: 1\n", encoding="utf-8")

        with open(path, encoding="utf-8") as handle:
            assert parse_yaml(handle) == {"a": 1}

    def test_it_accepts_bytes(self) -> None:
        assert parse_yaml(b"a: 1\n") == {"a": 1}

    def test_it_refuses_to_construct_arbitrary_objects(self) -> None:
        """`safe_` was the point of `safe_load`; a loader swap must not have widened it."""
        with pytest.raises(yaml.YAMLError):
            parse_yaml("!!python/object/apply:os.system ['echo unsafe']\n")


class TestWhatItRaises:
    @pytest.mark.parametrize(
        "malformed",
        [
            pytest.param("a: 1\n\tb: 2\n", id="tab-indent"),
            pytest.param("a: [1, 2\n", id="unclosed-flow-sequence"),
            pytest.param("a: 'unterminated\n", id="unterminated-quote"),
            pytest.param("*missing_anchor\n", id="undefined-alias"),
        ],
    )
    def test_malformed_input_raises_yamlerror(self, malformed: str) -> None:
        """The contract ~15 call sites depend on: `except yaml.YAMLError` still catches it.

        Both loaders raise subclasses of `YAMLError`, so this holds whichever one this install got —
        which is why it is asserted against the base class rather than a concrete subclass.
        """
        with pytest.raises(yaml.YAMLError):
            parse_yaml(malformed)


class TestItIsTheFastLoader:
    def test_libyaml_is_used_whenever_pyyaml_offers_it(self) -> None:
        """The entire point of the module, so it is asserted rather than assumed.

        Phrased as an implication so it holds on an install whose PyYAML was built without libyaml,
        where falling back to the pure-Python loader is correct.
        """
        assert USES_LIBYAML is hasattr(yaml, "CSafeLoader")


_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FENCED = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def _repository_yaml_documents() -> list[str]:
    """Every YAML document the repository actually stores: frontmatter, fenced blocks, ontology files."""
    model = _REPO_ROOT / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"
    documents: list[str] = []
    for path in list(model.rglob("*.md")) + list(model.rglob("*.puml")):
        # The renderer writes its scratch file into the catalog it is rendering from, so one can be
        # listed here and gone before it is read. It is not a document this repository stores.
        if is_render_scratch(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if match := _FRONTMATTER.match(text):
            documents.append(match.group(1))
        documents.extend(_FENCED.findall(text))
    documents.extend(p.read_text(encoding="utf-8") for p in (_REPO_ROOT / "src/ontologies").rglob("*.yaml"))
    return documents


def _outcome(parse: Callable[[], object]) -> object:
    """What a parse produced, with a refusal folded in as a comparable value.

    The corpus includes fenced blocks written to *illustrate* YAML in prose, some of which are not
    valid documents. A refusal is therefore a legitimate outcome, and the two parsers must agree on it
    — including on which error it is, which is why the type name is part of the value.
    """
    try:
        return parse()
    except yaml.YAMLError as exc:
        return f"error:{type(exc).__name__}"


def _parsed_or_error(text: str, loader: Any) -> object:
    return _outcome(lambda: yaml.load(text, Loader=loader))


@pytest.mark.skipif(not hasattr(yaml, "CSafeLoader"), reason="PyYAML built without libyaml")
def test_no_stored_document_parses_differently_under_the_two_loaders() -> None:
    """The swap's safety argument, checked against real content rather than invented cases.

    An invariant, not a count: it asserts that *no* document differs, so authoring more of them can
    only strengthen it.
    """
    documents = _repository_yaml_documents()
    assert documents, "found no stored YAML — the walk broke, and this test would pass on nothing"

    differing = [
        text[:120]
        for text in documents
        if _parsed_or_error(text, yaml.SafeLoader) != _parsed_or_error(text, yaml.CSafeLoader)
    ]

    assert differing == [], f"{len(differing)} stored document(s) parse differently: {differing[:3]}"


@pytest.mark.skipif(not hasattr(yaml, "CSafeLoader"), reason="PyYAML built without libyaml")
def test_parse_yaml_agrees_with_the_loader_it_replaced() -> None:
    """`parse_yaml` itself, not just the loaders, over the same corpus."""
    documents = _repository_yaml_documents()
    assert documents

    differing = [
        text[:120]
        for text in documents
        if _outcome(lambda t=text: parse_yaml(t)) != _parsed_or_error(text, yaml.SafeLoader)
    ]

    assert differing == [], f"{len(differing)} document(s) differ from `safe_load`: {differing[:3]}"
