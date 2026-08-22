"""Every syntax this project reads has exactly one module that decides how to read it.

**Why a register and not a seventh bespoke test.** The lesson here was learned three times and fixed
three times, and each fix was an instance: `yaml.safe_load` at 77 call sites, *fourteen* readings of a
frontmatter fence, and — found by a user in another checkout the day after 0.5.2 shipped — **five**
readings of a PlantUML alias declaration, which disagreed about whether a trailing `#colour` still
declares one. Each fix arrived with its own test naming its own owner in its own `_OWNER` constant.
Six such tests exist, 750 lines of them, and between them they enumerate nothing: there was no place
for "who reads a PUML declaration?" to be a *missing row*, so the answer was found by being hurt.

The syntaxes are 26 modules' worth of regexes over our own file formats. Three of them are owned and
now registered below. Adding a syntax to this register is a one-line act; the point is that adding a
*reader* without one is now a failing test rather than a thing somebody notices later.

**Two detectors, because a second reader announces itself in two ways.**

* *Reserved names* — the reader is a library call, so naming it is the decision (`yaml.safe_load`).
* *A literal probe* — the reader is ours, so the decision is a pattern handed to `re` or to a string
  search. Inspecting the **call** rather than the literal is load-bearing, and the frontmatter gate
  paid for that knowledge: scanning literals for three dashes reported markdown table separators and
  the `source---target` connection id. *Emitting* a syntax is not reading it, so a renderer that
  writes `as ALIAS` is untouched.

**What is deliberately not here.** Four of the six single-owner gates answer a different question and
folding them in would misfile them: `test_db_key_writes_go_through_the_guard` is a *write* guard whose
subject is which account a write may name; `test_closed_response_models_share_one_base` is a type-level
rule about a base class; `test_runtime_catalogs_have_one_accessor` owns a derivation rather than a
syntax; `test_backend_serves_from_one_process` is about processes. A register that claimed those would
be a register about nothing in particular.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources

#: Calls that *locate* something in text, as against composing it. One set for substring and pattern
#: searches alike, because both take the same evidence: a literal that spells the syntax.
_LOCATING_CALLS = frozenset({
    "find", "index", "rfind", "partition", "removeprefix", "startswith",
    "match", "fullmatch", "search", "sub", "subn", "compile", "split", "findall", "finditer",
})


@dataclass(frozen=True)
class SyntaxReader:
    """One syntax, the module that owns reading it, and how a second reader gives itself away."""

    #: What is read, in the words a reviewer would use.
    syntax: str
    #: The modules that decide it. Repository-relative, so moving one is a visible edit here. Usually
    #: one; two where a glyph genuinely serves two syntaxes this rule cannot tell apart.
    owners: tuple[Path, ...]
    #: What a caller must use instead. Named in the failure message, because a gate that refuses
    #: without saying where to go is a gate people route around.
    instead: str
    #: The incident this row exists because of. Not decoration: a row with no incident is a rule
    #: nobody can weigh against the cost of obeying it.
    incident: str
    #: Library callables and classes whose mere naming *is* the decision.
    reserved_names: frozenset[str] = frozenset()
    #: The module those names must be reached *through*. Required with `reserved_names`, and the
    #: reason is measured: matching a bare name reported twelve files for `load` alone — `json.load`,
    #: `index.load`, a catalog's own `load`. A reserved name is only a decision in its own namespace.
    reserved_module: str = ""
    #: A pattern that a literal must match to count as spelling this syntax.
    literal_probe: re.Pattern[str] | None = None
    #: Modules that legitimately read it anyway, each because of something this rule cannot see.
    exempt: frozenset[Path] = field(default_factory=frozenset)


#: Three dashes against a line boundary. Deliberately no bare start-of-string alternative: with one,
#: every literal *beginning* `---` matched, which reported `artifact_id.split("---")` — the connection
#: id separator, not a fence.
_ANCHORED_FENCE = re.compile(r"(?:\n|\\n|\\A|\^|\\r)-{3}|-{3}(?:\n|\\n|\\r|\\Z|\$|\[ \\t\])")

#: The section's own separator. Precise on purpose: an earlier version also matched a bare `###`
#: heading and reported two *display-block* readers (`### archimate`, `### <lang>`) that have nothing
#: to do with connections. A bare `###` is markdown and belongs to whoever reads markdown; what makes
#: a section a *connection* is the arrow.
_CONNECTION_SECTION = re.compile("→")

#: `as ALIAS` — PlantUML's alias declaration. The word plus whitespace is enough to distinguish it
#: from prose, and the trailing charset is what the five readings disagreed about.
_ALIAS_DECLARATION = re.compile(r"\\bas\\s|\bas\\s\+|\bas\s\+")

#: The direction alternation any reading of an arrow token needs, to know a token already states
#: one. A second implementation cannot avoid spelling it.
_ARROW_DIRECTION = re.compile(r"up\|down\|left\|right")

#: A markdown inline link. The bracket-then-paren shape is what every reading of one spells, and
#: nothing else in these formats does: a literal carrying `](` is reading a link.
_MARKDOWN_LINK = re.compile(r"\]\\?\(")

#: The sentinel link's opening. Anchored to the scheme, which is what any reading of one must spell:
#: a literal carrying `arch://` handed to a locating call is deciding where a step's id begins.
_SENTINEL_LINK = re.compile(r"arch://")

#: The kind prefix on a required-/suggested-reference term. Anchored to the whole literal, because
#: `doc:` and `diagram:` are short enough to appear inside prose that is not deciding anything; a
#: reader hands the prefix to `startswith` or `split` as exactly this string and nothing else.
_REFERENCE_TERM_PREFIX = re.compile(r"\A(doc|diagram):\Z")

SYNTAX_READERS: tuple[SyntaxReader, ...] = (
    SyntaxReader(
        syntax="what counts as a frontmatter block",
        owners=(Path("src/domain/repository/frontmatter.py"),),
        instead=(
            "`src.domain.repository.frontmatter`: `read_frontmatter` for the block, "
            "`parse_frontmatter` for the mapping, `body_after_frontmatter` to strip it, "
            "`replace_frontmatter_text` to rewrite it, `opens_with_frontmatter` for the cheap guard"
        ),
        incident=(
            "fourteen readings in five families that did not agree; the two loosest were the verifier "
            "and the document write path, so a file could be verified under one delimitation and "
            "rewritten under another"
        ),
        literal_probe=_ANCHORED_FENCE,
    ),
    SyntaxReader(
        syntax="how a YAML document is parsed",
        owners=(Path("src/domain/yaml_documents.py"),),
        instead="`src.domain.yaml_documents.parse_yaml`",
        incident=(
            "77 call sites each independently choosing the pure-Python loader on a machine with "
            "libyaml present; the C loader is 9.5x faster for identical results on this corpus"
        ),
        reserved_names=frozenset({
            "safe_load", "safe_load_all", "load", "load_all", "full_load", "unsafe_load",
            "SafeLoader", "CSafeLoader", "Loader", "CLoader", "FullLoader", "UnsafeLoader",
        }),
        reserved_module="yaml",
    ),
    SyntaxReader(
        syntax="what it means for a PUML line to declare an alias",
        owners=(Path("src/application/puml_alias_declarations.py"),),
        instead=(
            "`src.application.puml_alias_declarations`: `alias_declared_on` for one line, "
            "`declared_aliases` for a body, `macro_alias_declared_on` for the macro form"
        ),
        incident=(
            "five readings disagreeing on whether a trailing `#colour` still declares an alias, on "
            "whether a hyphen belongs to one, and on whether quoted prose can look like one — so a "
            "body drawing a junction lost it from `entity-ids-used` and the verifier refused the "
            "diagram (E315) for omitting an entity the writer had dropped"
        ),
        literal_probe=_ALIAS_DECLARATION,
        exempt=frozenset({
            # Reads the *legacy* GSN body form as a triple — element kind, quoted label, alias — to
            # draw native SVG, and the shared reading answers only the alias. Exempted rather than
            # converted because it is not the defect: its pattern matches mid-line, so a trailing
            # colour does not defeat it, and it is confined to one diagram type's own round trip.
            # The drift risk is real and recorded as its own item rather than fixed under a defect
            # release, which is where a second reader gets converted without its own test pass.
            Path("src/diagram_types/gsn/svg_renderer.py"),
        }),
    ),
    SyntaxReader(
        syntax="where a direction or line style goes inside a PUML arrow token",
        owners=(Path("src/application/puml_arrow_tokens.py"),),
        instead=(
            "`src.application.puml_arrow_tokens`: `insert_arrow_direction` to rank a pair, "
            "`insert_arrow_line_style` to restyle its line"
        ),
        incident=(
            "three implementations of the direction insert — the renderer's, the layout optimiser's "
            "that rewrites stored bodies, and a third in `diagram_builder` no caller had reached "
            "since it was copied. The two live ones agreed, which is why nothing failed and nothing "
            "reported them; then the containment arrows `o--` and `*--` needed a token form neither "
            "knew, and a fix applied to the renderer alone would have left the optimiser silently "
            "dropping the direction from every arrow it rewrote"
        ),
        literal_probe=_ARROW_DIRECTION,
    ),
    SyntaxReader(
        syntax="what a document's prose refers to — a markdown link and the file it addresses",
        owners=(Path("src/application/document_links.py"),),
        instead=(
            "`src.application.document_links`: `references_from` for what a body points at, "
            "`references_to_entity` for what points at one entity, `iter_markdown_links` for the "
            "links alone where the target does not matter"
        ),
        incident=(
            "three readings of one question. The cascade-delete preflight matched `](….md)` with a "
            "regex of its own, which cannot match `](….md#properties)` — so a document linking into "
            "a *section* of an entity was invisible to the check whose whole job is to find what a "
            "deletion would break; the verifier's unresolvable-link rule spelled the link a third "
            "way and was never asked about a diagram, where every dangling link in this repository "
            "turned out to be. Reference-typed attributes would have been the fourth"
        ),
        literal_probe=_MARKDOWN_LINK,
        exempt=frozenset({
            # Reads the *documentation* tree rather than the model: `docs/**.md` links, anchors and
            # media references, including image and non-markdown targets that the model's own link
            # rules deliberately say nothing about. It is a build tool with its own gate, and the
            # two answer different questions about different trees.
            Path("tools/docs/check_doc_links.py"),
        }),
    ),
    SyntaxReader(
        syntax="the arrow form of a connection — a `###` section, or a standalone reference",
        owners=(
            # Two owners on purpose, because this is two syntaxes sharing one glyph and a literal
            # probe cannot see which: `connection_declaration` owns the arrow *inside* a `###`
            # section of an `.outgoing.md`, `artifact_id` owns it in a standalone reference
            # (`source type → target`, the form bulk operations and promotion accept). Splitting
            # this into two rows made each flag the other's owner, which is a fact about the probe
            # rather than a finding — and cross-exempting them would have put two non-debts into a
            # budget whose whole value is that it only holds debt.
            Path("src/domain/repository/connection_declaration.py"),
            Path("src/domain/artifact_id.py"),
        ),
        instead=(
            "for a section: `src.domain.repository.connection_declaration` — "
            "`parse_connection_declarations` for a file, `parse_connection_header` for one header, "
            "`format_connection_declaration` to write one, and it already has the format→parse round "
            "trip in `tests/domain/`. For a standalone reference: "
            "`src.domain.artifact_id.parse_connection_reference`, which answers a named record so the "
            "field order cannot be transposed again"
        ),
        incident=(
            "eight modules spelled the section themselves after it was given an owner — three "
            "hand-rolling the multiplicity stripping the parser already does — and the standalone "
            "reference had three readings that disagreed on `split` versus `rsplit`, on stripping, "
            "and on the *tuple order*: `(source, target, type)` in the bulk and sync readers against "
            "`(source, type, target)` in the promotion planner, so moving a caller between two "
            "functions of the same shape would have transposed target and type with nothing to catch it"
        ),
        literal_probe=_CONNECTION_SECTION,
        #: **Shrink-only.** Eight second readers were measured; five are gone, three are here with a
        #: reason. Adding a ninth fails this test, which is the point.
        #:
        #: The three that remain **rewrite** files rather than read them: cascade delete removes the
        #: sections naming a deleted entity, promotion retargets a header in place
        #: (`re.sub(rf"(^### .+? → ){{re.escape(old_id)}}$", …)`), and cleanup counts and strips
        #: broken ones. The owner exposes `parse` and `format`, not "retarget a declaration" or
        #: "remove those naming X" — so converting them means designing those primitives onto the
        #: aggregate, and getting one wrong corrupts model files rather than failing a test. That is
        #: its own change with its own tests, not a line in a defect release.
        #:
        exempt=frozenset({
            Path("src/infrastructure/write/artifact_write/_cascade_helpers.py"),
            Path("src/infrastructure/write/artifact_write/_promote_file_ops.py"),
            Path("src/infrastructure/write/artifact_write/cleanup_broken_refs.py"),
        }),
    ),
    SyntaxReader(
        syntax="which vocabulary a required-/suggested-reference term names",
        owners=(Path("src/application/artifacts/reference_terms.py"),),
        instead=(
            "`src.application.artifacts.reference_terms`: `parse_reference_term` for the kind and "
            "the name within it, `ReferenceTermVocabulary` for whether it expands here, what a link "
            "of that kind would satisfy, and how to say it in a message"
        ),
        incident=(
            "a row written when the vocabulary widened rather than after it went wrong. The "
            "entity-only pair it replaced was named literally at thirteen sites across the loader, "
            "the verifier, the promotion closure, the placeholder writer, two REST contracts and "
            "four GUI modules — and a term whose kind each of those decided for itself is the same "
            "shape as the PUML alias declaration that five modules disagreed about"
        ),
        literal_probe=_REFERENCE_TERM_PREFIX,
    ),
    SyntaxReader(
        syntax="the sentinel link naming the step a rendered activity line stands for",
        owners=(Path("src/diagram_types/activity/_step_links.py"),),
        instead=(
            "`src.diagram_types.activity._step_links`: `sentinel_wrapped` and `link_suffix` to "
            "write one, `sentinel_of` to read one off a line, `drawn_step_ids` for a whole body"
        ),
        incident=(
            "a row written when the first reader arrived, not after a second one hurt. The step "
            "coverage diagnostic had to answer whether a stored body draws a declared step, and the "
            "sentinel is written in two forms — after the label, and as a clause of its own — that "
            "end the id differently, one at a space and one at a bracket, with `]` escaped in both. "
            "Nothing had ever read it back in Python, and the emission gained two new line kinds in "
            "the same release, so a reader that stopped at the wrong delimiter would have reported "
            "every step of a partition undrawn and nobody would have known which side was wrong"
        ),
        literal_probe=_SENTINEL_LINK,
    ),
)

#: What each row's exemptions cost today. A ratchet in the spirit of the project's other shrink-only
#: registers: the number may fall and may never rise, so a twelfth reader cannot arrive quietly by
#: being added to a list.
_EXEMPTION_BUDGET: dict[str, int] = {
    "what a document's prose refers to — a markdown link and the file it addresses": 1,
    "what it means for a PUML line to declare an alias": 1,
    "the arrow form of a connection — a `###` section, or a standalone reference": 3,
}


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


def _names_used(path: Path, reserved: frozenset[str], module: str) -> list[str]:
    """Every reserved name this file reaches for *through `module`* — by attribute or from-import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound_to_module = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == module
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in bound_to_module
            and node.attr in reserved
        ):
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module == module:
            found.update(alias.name for alias in node.names if alias.name in reserved)
    return sorted(found)


def _literals_deciding(path: Path, probe: re.Pattern[str]) -> list[str]:
    """Literals this file hands to a locating call that spell the syntax itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        literal = _first_string_argument(node)
        if literal is None or _called_name(node) not in _LOCATING_CALLS:
            continue
        if probe.search(literal):
            found.add(literal)
    return sorted(found)


def _second_readers(reader: SyntaxReader) -> dict[str, list[str]]:
    offenders: dict[str, list[str]] = {}
    for path in python_sources(SRC, TOOLS):
        relative = path.relative_to(REPO_ROOT)
        if relative in reader.owners or relative in reader.exempt:
            continue
        found = (
            _names_used(path, reader.reserved_names, reader.reserved_module)
            if reader.reserved_names
            else []
        )
        if reader.literal_probe is not None:
            found += _literals_deciding(path, reader.literal_probe)
        if found:
            offenders[str(relative)] = found
    return offenders


@pytest.mark.parametrize("reader", SYNTAX_READERS, ids=lambda reader: str(reader.owners[0].stem))
def test_the_owner_is_where_the_register_says_it_is(reader: SyntaxReader) -> None:
    """Without this, moving a module would make its row vacuously satisfied."""
    for owner in reader.owners:
        assert (REPO_ROOT / owner).is_file(), f"{owner} owns {reader.syntax} and is not there"


@pytest.mark.parametrize("reader", SYNTAX_READERS, ids=lambda reader: str(reader.owners[0].stem))
def test_nothing_outside_the_owner_decides_the_syntax(reader: SyntaxReader) -> None:
    offenders = _second_readers(reader)

    assert offenders == {}, (
        f"these decide {reader.syntax} themselves, which is how this went wrong before "
        f"({reader.incident}). Use {reader.instead}. {offenders}"
    )


@pytest.mark.parametrize("reader", SYNTAX_READERS, ids=lambda reader: str(reader.owners[0].stem))
def test_every_row_carries_the_incident_that_earned_it(reader: SyntaxReader) -> None:
    """A rule with no recorded cost is one the next reader argues with rather than obeys."""
    assert len(reader.incident) > 80, (reader.syntax, reader.incident)
    assert reader.reserved_names or reader.literal_probe is not None, reader.syntax
    # A namespace-less reserved name matches anything spelled the same anywhere.
    assert bool(reader.reserved_names) == bool(reader.reserved_module), reader.syntax


@pytest.mark.parametrize("reader", SYNTAX_READERS, ids=lambda reader: str(reader.owners[0].stem))
def test_no_row_carries_more_exemptions_than_its_budget(reader: SyntaxReader) -> None:
    """Shrink-only. A twelfth reader may not arrive by being added to a list."""
    budget = _EXEMPTION_BUDGET.get(reader.syntax, 0)

    assert len(reader.exempt) <= budget, (
        f"{reader.syntax}: {len(reader.exempt)} exempted readers against a budget of {budget}. "
        "Convert the reader instead of exempting it; lower the budget when one goes."
    )


class TestTheDetectorsCatchWhatTheyClaim:
    """Applied to snippets, so the guard is tested rather than trusted — each is a real past reading."""

    @pytest.mark.parametrize(
        "reading",
        [
            pytest.param(r'''re.compile(r"\bas\s+([A-Za-z0-9_-]+)\s*\{?\s*$")''', id="end-anchored"),
            pytest.param(r'''re.compile(r'\bas\s+(?P<alias>[A-Za-z0-9_]+)\s*(\{\s*)?$')''', id="grouping"),
            pytest.param(r'''re.compile(r"\bas\s+(?P<alias>[A-Za-z0-9_-]+)\s*\{\s*$")''', id="container"),
            pytest.param(r'''re.search(r"\bas\s+(\w+)", without_quotes)''', id="tolerant"),
        ],
    )
    def test_each_of_the_five_alias_readings_is_recognised(self, reading: str) -> None:
        tree = ast.parse(reading)
        decisions = [
            literal
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (literal := _first_string_argument(node)) is not None
            and _called_name(node) in _LOCATING_CALLS
            and _ALIAS_DECLARATION.search(literal)
        ]

        assert decisions, reading

    @pytest.mark.parametrize(
        "reading",
        [
            pytest.param(r'''re.search(r"(up|down|left|right)", arrow)''', id="renderer"),
            pytest.param(r'''re.search(r"(up|down|left|right|hidden)", arrow)''', id="line-style"),
        ],
    )
    def test_each_arrow_direction_reading_is_recognised(self, reading: str) -> None:
        """Both live copies spelled the alternation; the third, dead one did too."""
        tree = ast.parse(reading)
        decisions = [
            literal
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (literal := _first_string_argument(node)) is not None
            and _called_name(node) in _LOCATING_CALLS
            and _ARROW_DIRECTION.search(literal)
        ]

        assert decisions, reading

    @pytest.mark.parametrize(
        "innocent",
        [
            pytest.param('f\'rectangle "{label}" as {alias}\'', id="emitting-a-declaration"),
            pytest.param('lines.append(f"{indent}rectangle as {group_alias} {{")', id="emitting-a-container"),
            pytest.param('artifact_id.split("---")', id="connection-id-separator"),
            pytest.param('name.startswith("archimate")', id="unrelated-prefix"),
        ],
    )
    def test_composing_a_syntax_is_not_reading_it(self, innocent: str) -> None:
        tree = ast.parse(innocent)
        decisions = [
            literal
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (literal := _first_string_argument(node)) is not None
            and _called_name(node) in _LOCATING_CALLS
            and (_ALIAS_DECLARATION.search(literal) or _ANCHORED_FENCE.search(literal))
        ]

        assert decisions == [], innocent
