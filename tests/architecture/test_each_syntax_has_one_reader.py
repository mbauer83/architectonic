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
    "find", "index", "rfind", "partition", "removeprefix", "startswith", "endswith", "removesuffix",
    "match", "fullmatch", "search", "sub", "subn", "compile", "split", "findall", "finditer",
})

#: Asking a parsed element for an attribute. For a syntax read out of a parsed tree this locates as
#: surely as searching the markup does — but only for such a syntax: a mapping's `get` takes a key,
#: and added for every row it reported a dictionary lookup of an icon fence's name as a reading of it.
_ATTRIBUTE_LOOKUPS = frozenset({"get"})


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
    #: Calls that locate this syntax beyond `_LOCATING_CALLS`, where it is read some other way.
    also_located_by: frozenset[str] = frozenset()
    #: Where this syntax is read *only* by these calls, in place of `_LOCATING_CALLS`: a glyph so
    #: common (a dot) that splitting at it is no evidence, while cutting at the last one is.
    only_located_by: frozenset[str] = frozenset()
    #: A pattern two or more literals of one tuple, list, set or dict display must match for that
    #: display to count as stating the syntax's values — and so their order. For a syntax that is a
    #: ranked vocabulary, whose second reader is a table of the values rather than a search for one.
    enumeration_probe: re.Pattern[str] | None = None
    #: Modules that legitimately read it anyway, each because of something this rule cannot see.
    exempt: frozenset[Path] = field(default_factory=frozenset)


#: The markers of the embedded-icon block at the top of a body.
_ICON_BLOCK_MARKER = re.compile(r"arch-icons:(?:begin|end)")

#: The fence an icon file's render form sits in.
_ICON_RENDER_FENCE = re.compile(r"png-base64")

#: The `data:` URI of an embedded image, as something a value is tested for.
_DATA_IMAGE_URI = re.compile(r"data:image")

#: The outgoing-connections file name, as a test of what a file is. Writers compose the name
#: (`with_suffix`, a glob) and are not readings; asking a name whether it ends so is.
_OUTGOING_FILE = re.compile(r"^\.outgoing\.md$")

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

#: The head of a stereotype styling declaration. Anchored to `rectangle<<` with nothing between,
#: which is what PlantUML's skinparam form spells and what a reading of one cannot avoid.
#:
#: **Not the bare `<<Name>>`**, deliberately. That glyph is also how an arrow names its relation type
#: and how an element line names its stereotype, and those have several readers doing genuinely
#: different jobs — the grouping parser, the relation parsers, the verifier's rules. Probing for it
#: would report five modules that are not deciding *this* question, and a register that cries wolf is
#: the register nobody keeps. What has one owner, and is registered here, is the declaration.
_STEREOTYPE_STYLING_HEAD = re.compile(r"rectangle<<")

#: The kind prefix on a required-/suggested-reference term. Anchored to the whole literal, because
#: `doc:` and `diagram:` are short enough to appear inside prose that is not deciding anything; a
#: reader hands the prefix to `startswith` or `split` as exactly this string and nothing else.
_REFERENCE_TERM_PREFIX = re.compile(r"\A(doc|diagram):\Z")

#: The release version form, as a regex source would spell it: three integer groups joined by
#: escaped dots. A second reader of `MAJOR.MINOR.PATCH` is a second opinion on how two versions order.
_RELEASE_VERSION_FORM = re.compile(r"\\d\+\\\.\\d\+\\\.\\d\+")

#: The digest half of a `SHA256SUMS` line as a regex source spells it: sixty-four hex characters.
_CHECKSUM_DIGEST = re.compile(r"\[0-9a-f(A-F)?\]\{64\}")

#: A literal that *opens* with a pipe: the bare glyph a row is split on, a row's opening `| `, a
#: delimiter row's `|---`, or any of them as a pattern spells it. Every table reading there has been
#: handed one of these to `split` or `startswith`.
#:
#: **Not a pipe anywhere in the literal**, which is every regex alternation in the codebase. And the
#: bare glyph is kept in, although it is also how a few joined keys are separated: leaving it out
#: would miss `split("|")`, which is the whole of two of the three readings this row replaced. The
#: price is that a module separating something else by a pipe must *name* its separator — which the
#: activity lane bound and the result-type alternative now do — or stand in the exemptions as the
#: unowned syntax it is.
_TABLE_PIPE = re.compile(r"\A(?:\^|\\A)?(?:\\s\*|\s*)\\?\|")

#: The prefix of a provisional reference. A literal carrying it, handed to a locating call, is
#: deciding where an alias begins. JSON Schema's bare `"$ref"` key has no colon and is not this.
_PROVISIONAL_REFERENCE = re.compile(r"\$ref:")

#: The attributes PlantUML names a drawn shape and a relation's two ends by. Any reading of a
#: rendered picture's structure has to spell one of them, whether it asks an element for the
#: attribute or searches the markup for it.
_RENDERED_SHAPE_NAMING = re.compile(r"data-qualified-name|data-entity-[12]|data-link-type|data-diagram-type")

#: The markers of the three boxes a renderer computes, as a test of what an alias is. Anchored to the
#: start because that is the only place a marker means anything, and the underscore keeps the probe
#: off prose that merely mentions a domain.
_COMPUTED_BOX_MARKER = re.compile(r"\A\^?(DOM|GRPT|GRPA)_")

#: The key a section of a document type declares its typed tables under, as something a mapping is
#: asked for. Anchored to the whole literal: the word is common in prose and in SQL, and only a lookup
#: of exactly this key is a reading of the declaration.
_TABLE_DECLARATION_KEY = re.compile(r"\Atables\Z")

#: What separates the two end instances in a drawn-relation key. The whole literal, because the
#: glyph is common inside longer ones; a reader of a key hands exactly this to `partition` or `split`.
_RELATION_ENDS_SEPARATOR = re.compile(r"\A>\Z")

#: The prefix of a rule key. A literal carrying it, handed to a locating call, is deciding whether a
#: layout key addresses a box by its rule.
_RULE_KEY_PREFIX = re.compile(r"\Arule:")

#: The dot an artifact id's slug follows, handed to a call that cuts or counts at it: deciding which
#: part of an id is its stable identity. Only those calls (`only_located_by`): a `split(".")` over a
#: dotted version or a file name is not a reading of an id, and was the noise a broader probe met.
_ID_SLUG_SEPARATOR = re.compile(r"\A\.\Z")
_CUTS_AT_THE_SLUG = frozenset({"rsplit", "rpartition", "count"})

#: Two words only a reading of the layout block asks a mapping for: where a relation bends, and the
#: section that sizes boxes. Whole literals, and deliberately not `layout` itself — a diagram type's
#: configuration and a scratchpad's document each have a `layout` of their own that is not this one.
_LAYOUT_BLOCK_WORD = re.compile(r"\A(via|boxes)\Z")

#: A Traffic Light Protocol level, spelled whole.
_TLP_LEVEL = re.compile(r"\ATLP:[A-Z]+\Z")

SYNTAX_READERS: tuple[SyntaxReader, ...] = (
    SyntaxReader(
        syntax="the stored candidate architecture document",
        owners=(Path("src/application/change_sets/candidate_recorded_form.py"),),
        instead="load_candidate and dump_candidate, delegating operations to recorded_form",
        incident="The index, verifier and candidate store must agree on the same recorded architecture.",
        literal_probe=re.compile(r"^\.candidate\.yaml$"),
    ),
    SyntaxReader(
        syntax="the typed tables a document type's section declares, and the form of a row's id",
        owners=(Path("src/application/artifacts/document_tables.py"),),
        instead=(
            "`src.application.artifacts.document_tables`: `table_declarations` for what a type's "
            "sections declare — reached as `SectionSpec.tables` — `TableSpec.row_schema` for the JSON "
            "Schema of a row, `TableSpec.row_id` and `row_number` to write and read an id, "
            "`format_row_ids` and `row_ids_in` for a cell naming several, `TableSpec.scaffold` for the "
            "empty table. For a document's rows as typed values, "
            "`src.application.artifacts.document_table_rows.read_document_tables`"
        ),
        incident=(
            "a row written with the syntax and not after a second reader hurt. The declaration is "
            "served to a browser, scaffolded by the write path, read by the verifier and will be "
            "edited row by row — four consumers of a column's type, its title and its row-id form. "
            "The loader already normalises a schema file, serialises it and normalises it again, so a "
            "consumer taking the raw `tables` list from that dictionary instead of the specification "
            "would read a column without its defaults and a row id without its table's prefix, which "
            "is the same shape as the reference-term prefix that thirteen sites each decided"
        ),
        literal_probe=_TABLE_DECLARATION_KEY,
        also_located_by=_ATTRIBUTE_LOOKUPS,
    ),
    SyntaxReader(
        syntax="a markdown table — where one is, its rows, and the cells of a row",
        owners=(Path("src/domain/markdown_table.py"),),
        instead=(
            "`src.domain.markdown_table`: `tables_in` for the tables of a text, `row_cells` for one "
            "row, `format_table` and `format_row` to write, `escape_cell` and `unescape_cell` between "
            "plain text and a cell. For an entity's `## Properties`, "
            "`src.domain.repository.properties_section`: `read_properties` and "
            "`format_properties_section`"
        ),
        incident=(
            "three readings of an entity's Properties table and two of a matrix row, none of which "
            "could read what the writer wrote: the writer escapes a pipe in a value and all three "
            "readers split at it, so `a|b` came back as `a\\` from every one of them. The "
            "index and the editor also took any row "
            "holding three hyphens for the delimiter row — a connection id as a value vanished — and "
            "any attribute named `Attribute` for the header, while the verifier read both; the "
            "verifier alone dropped empty cells before counting them, so it and the index disagreed "
            "about which cell was the value. The matrix rule called any text with a pipe in it, "
            "frontmatter included, a table"
        ),
        literal_probe=_TABLE_PIPE,
        #: **Shrink-only, and none of these reads a table.** Each splits a *joined key* on the pipe
        #: that joins it, and each key has more than one reader of its own and no row here: the
        #: derivation path key (`id@fwd|id@rev`), whose two readings disagree on a step without an
        #: orientation, and the index roots key, split at six sites. They stand here because the
        #: probe cannot tell their glyph from a table's, and they leave when each key has an owner
        #: that names its separator — which is its own change, with its own round trip.
        exempt=frozenset({
            Path("src/domain/relationships/relationship_path_reconstruction.py"),
            Path("src/application/derivation/refresh.py"),
            Path("src/infrastructure/mcp/artifact_mcp/context.py"),
            Path("src/infrastructure/mcp/artifact_mcp/_diagram_binding_modes.py"),
        }),
    ),
    SyntaxReader(
        syntax="a provisional reference — `$ref:<alias>`, naming what a batch has not created yet",
        owners=(Path("src/domain/provisional_reference.py"),),
        instead=(
            "`src.domain.provisional_reference`: `provisional` to write one, `alias_of` to ask "
            "whether a reference is one and what it names, `name_in` for the alias or the id"
        ),
        incident=(
            "a row written when the fourth reader was about to arrive. The bulk write resolved the "
            "form with `startswith` and a slice of five characters, the scratchpad lift took it off "
            "twice with `removeprefix`, and four writers composed it as an f-string — and a change "
            "set, whose operations name the entities it creates the same way, needed to read it "
            "again. Nothing had failed yet; the three readings agreed only because the form has "
            "never changed"
        ),
        literal_probe=_PROVISIONAL_REFERENCE,
    ),
    SyntaxReader(
        syntax="the release version — `MAJOR.MINOR.PATCH`, with or without its tag's `v`",
        owners=(Path("src/application/software_update/version.py"),),
        instead=(
            "`src.application.software_update.version`: `parse_release_version` for the reading, "
            "`ReleaseVersion` for ordering and `.tag` for the spelling"
        ),
        incident=(
            "registered with its owner rather than after an incident: `arch-update` compares the "
            "installed version with a release's, and a second reading that ordered `0.10` before "
            "`0.9` lexically would offer a downgrade as an update"
        ),
        literal_probe=_RELEASE_VERSION_FORM,
    ),
    SyntaxReader(
        syntax="a `SHA256SUMS` line — the digest, two spaces, the file name",
        owners=(Path("src/application/software_update/release.py"),),
        instead=(
            "`src.application.software_update.release.ChecksumStatement.parse`, and `verify_asset` to "
            "compare bytes against every digest a release states"
        ),
        incident=(
            "registered with its owner: the file is one of two independent digest statements an "
            "installed asset must agree with, and a reader that accepted a shorter hex run would "
            "accept a truncated statement"
        ),
        literal_probe=_CHECKSUM_DIGEST,
    ),
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
        syntax="the block of embedded icon pictures at the top of a PlantUML body",
        owners=(Path("src/application/puml_icon_header.py"),),
        instead=(
            "`src.application.puml_icon_header`: `with_icon_block` to write it, `embedded_icons` and "
            "`referenced_icon_keys` to read it"
        ),
        incident=(
            "none yet, and on purpose: the block is what the body policy trusts an icon variable by, "
            "so a second reading that disagreed about where the block ends would let an assignment "
            "outside it pass as one inside it"
        ),
        literal_probe=_ICON_BLOCK_MARKER,
    ),
    SyntaxReader(
        syntax="an icon file: its frontmatter fields and its fenced `png-base64` and `svg` blocks",
        owners=(Path("src/domain/icons/icon_file.py"),),
        instead="`src.domain.icons.icon_file`: `read_icon_file` and `format_icon_file`, one pair",
        incident=(
            "none yet, and on purpose: the icon file arrived in 0.11.0 with a writer and a reader in "
            "one module and a round-trip test over what the format permits, because every other "
            "syntax in this register gained its second reader before anyone asked who owned it"
        ),
        literal_probe=_ICON_RENDER_FENCE,
    ),
    SyntaxReader(
        syntax="an image embedded in text as a `data:image/…;base64,…` URI",
        owners=(Path("src/domain/embedded_image.py"),),
        instead="`src.domain.embedded_image.embedded_image`, then accept or refuse its `subtype`",
        incident=(
            "the PlantUML body policy and the uploaded-SVG sanitiser each spelled the URI: the policy "
            "matched only its prefix, the sanitiser the whole URI with two subtypes, so a payload "
            "one accepted the other refused, for a value both call an embedded image"
        ),
        literal_probe=_DATA_IMAGE_URI,
    ),
    SyntaxReader(
        syntax="which kind of artifact a repository file is, from where it sits and its name",
        owners=(Path("src/domain/repository/artifact_location.py"),),
        instead=(
            "`src.domain.repository.artifact_location`: `artifact_kind_at` for a path relative to its "
            "repository (`artifact_kind_declared_at` for the kind's row and its facts), "
            "`model_file_kind` for a file already known to sit under a model root"
        ),
        incident=(
            "four readings of one question disagreed: the incremental index made every `.md` it did "
            "not recognise an entity, so a README or a project note entered the index as one after "
            "a single update while a full scan indexed nothing; `artifact_verify` took any `.puml` "
            "for a diagram; the save dialog knew only the top-level `model/` and so listed no entity "
            "under `projects/<slug>/model/`; the bulk inventory made every non-diagram an entity"
        ),
        literal_probe=_OUTGOING_FILE,
    ),
    SyntaxReader(
        syntax="how a YAML document is parsed",
        owners=(Path("src/domain/yaml_documents.py"),),
        instead=(
            "`src.domain.yaml_documents.parse_yaml`, or its strict mode `parse_yaml_with_unique_keys` "
            "where a key named twice must be refused rather than silently keep its last value"
        ),
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
    SyntaxReader(
        syntax="how a stereotype's own styling is declared, and whether a body is using it",
        owners=(Path("src/infrastructure/rendering/_archimate_includes.py"),),
        instead=(
            "`src.infrastructure.rendering._archimate_includes.ArchimateDeclarations`: "
            "`referenced_in` for which declarations a body *uses*, `notation_of` for how one kind is "
            "drawn, `are_inlined_in` and `restated_in` for a body that carries its own copies"
        ),
        incident=(
            "a row written after the two questions this syntax answers were read as one. Styling a "
            "stereotype and drawing one are spelled with the same `<<Name>>`, and `referenced_in` "
            "matched it anywhere — so every stored diagram, which inlines its own skinparam blocks, "
            "reported each kind it styles as a kind it draws. The legend read that as \"this fill is "
            "still on screen\" and named a colour no element carried: with the element-kind colouring "
            "removed, every box was neutral and the legend still sent a reader looking for purple. "
            "The comment on the pattern had claimed \"on an element line\" since it was written"
        ),
        literal_probe=_STEREOTYPE_STYLING_HEAD,
    ),
    SyntaxReader(
        syntax="the structure of the SVG PlantUML renders — which group is a shape or a relation, and what names it",
        owners=(
            # One reading in two modules, split for length: the picture and its shapes, and a
            # relation's ends. Both are reached only through `read_rendered_picture`.
            Path("src/infrastructure/rendering/layout/plantuml_svg_reader.py"),
            Path("src/infrastructure/rendering/layout/_svg_relations.py"),
        ),
        instead=(
            "`src.infrastructure.rendering.layout.plantuml_svg_reader.read_rendered_picture`, which "
            "answers a `RenderedPicture` by alias or a `NotReadable` naming what it met; resolve an "
            "alias to an instance with `archimate_occurrences.instance_by_alias`"
        ),
        incident=(
            "registered with its owner, because the structure is another project's output and not a "
            "contract it has promised: a layout is harvested from this reading and written back, so a "
            "second reader that kept going past a group it did not recognise would write a diagram "
            "with elements silently missing — and the first reading of it here was a throwaway "
            "harvest that did exactly that, skipping any relation whose end it could not find"
        ),
        literal_probe=_RENDERED_SHAPE_NAMING,
        also_located_by=_ATTRIBUTE_LOOKUPS,
    ),
    SyntaxReader(
        syntax="which kind of box an alias on a picture names — a domain's, a type's, an authored grouping's",
        owners=(Path("src/domain/diagrams/layout/box_aliases.py"),),
        instead=(
            "`src.domain.diagrams.layout.box_aliases`: `domain_box_alias`, `type_box_alias` and "
            "`authored_grouping_alias` to write one, `box_kind` to read one back"
        ),
        incident=(
            "registered when the first reader arrived: the three markers were spelled in three "
            "renderer modules and read by nothing, and a picture keeps nothing else of which box is "
            "which. A reader spelling them a fourth time would have gone on calling a renamed box an "
            "authored grouping, and a layout keyed by box kind would have filed it under the wrong rule"
        ),
        literal_probe=_COMPUTED_BOX_MARKER,
    ),
    SyntaxReader(
        syntax="the layout block of a diagram's frontmatter — its sections, a placement, a port, a route",
        owners=(Path("src/domain/diagrams/layout/layout_block.py"),),
        instead=(
            "`src.domain.diagrams.layout.layout_block`: `read_layout` for the value a parsed block "
            "states (it refuses what is not one, with a sentence), `layout_as_written` for the mapping "
            "a frontmatter holds, `LAYOUT_KEY` for the key; the frontmatter itself is read and written "
            "by its own owners"
        ),
        incident=(
            "none, and on purpose: the block arrived with one reader, one writer and a round trip "
            "stated over what it permits, written into a diagram that holds what it names. It is read "
            "by the write path, the file writer, the verifier and, later, a composer and an editor; a "
            "second reading that took a port for a point, or kept a size the block states half of, "
            "would draw a picture the verifier had passed as another one"
        ),
        literal_probe=_LAYOUT_BLOCK_WORD,
        also_located_by=_ATTRIBUTE_LOOKUPS,
    ),
    SyntaxReader(
        syntax="the key of a drawn relation — a connection id, and its end instances where one is an occurrence",
        owners=(Path("src/domain/diagrams/relation_key.py"),),
        instead=(
            "`src.domain.diagrams.relation_key`: `drawn_relation_key` to write one, `read_relation_key` "
            "to read one in canonical spelling, `labels_by_relation` for a stored `edge-labels` mapping, "
            "`alias_pair_of` for the retired form; `src.domain.diagrams.drawn_relations` for which "
            "relations a diagram draws and under which keys"
        ),
        incident=(
            "the key it replaced was composed and read at five sites as `f\"{src}:{tgt}\"` — two "
            "renderers, the diagram context, the verifier and the write path — and could not tell two "
            "relations between one pair apart, so a label meant for a flow was drawn on the serving "
            "beside it. An edge label and a layout route are both filed under this key; two readings "
            "of it would put a label on one arrow and its route on another"
        ),
        literal_probe=_RELATION_ENDS_SEPARATOR,
    ),
    SyntaxReader(
        syntax="a rule key — `rule:domain=business/type=…`, addressing a box no grouping states",
        owners=(Path("src/domain/diagrams/authored_groupings.py"),),
        instead=(
            "`src.domain.diagrams.authored_groupings`: `RuleKey(...).text` to write one, `read_rule_key` "
            "to read one, `is_rule_key` to ask whether a key is spelled as one; `rule_of` for the rule "
            "a grouping entry states"
        ),
        incident=(
            "registered with its owner: a computed box had no identity but a renderer's counter, "
            "which two renders of a changed diagram need not agree on. A layout addresses such a box "
            "by this key, so a second reading that ordered the rules differently would size one "
            "domain's box with another's rectangle"
        ),
        literal_probe=_RULE_KEY_PREFIX,
    ),
    SyntaxReader(
        syntax="which spelling of an artifact id is its identity — the short form, or the id with its slug",
        owners=(Path("src/domain/artifact_id.py"),),
        instead=(
            "`src.domain.artifact_id`: `canonical_entity_key` to compare or key ids in either spelling, "
            "`stable_id` for the short form of an id known to be one, `parse_entity_id(...).long(slug)` "
            "to spell one with a new slug"
        ),
        incident=(
            "0.12.0's candidate and stress-analysis surfaces compared ids as strings, so the short form "
            "of an id meant something else than its slugged form in six places at once: a candidate "
            "read by its short id answered 404, an overlap check missed two renames of one element, a "
            "connection to an entity the candidate created was refused as joining nothing, an "
            "incidence hit read as missing, a residuality went unfound, and an occurrence was stored "
            "and never drawn. A rename's id was meanwhile composed by cutting at the last dot, which "
            "for a short id cuts off its random key"
        ),
        literal_probe=_ID_SLUG_SEPARATOR,
        only_located_by=_CUTS_AT_THE_SLUG,
        exempt=frozenset({
            # A browser asset's file extension, read from the last path segment: not an id.
            Path("src/infrastructure/backend/_spa_static.py"),
            # Whether a kind's file suffix is a plain extension or compound (`.outgoing.md`): not an id.
            Path("src/domain/repository/artifact_location.py"),
        }),
    ),
    SyntaxReader(
        syntax="a TLP classification level, and how two of them order",
        owners=(Path("src/domain/assurance/classification.py"),),
        instead=(
            "`src.domain.assurance.classification`: `exceeds_ceiling` to decide whether a reader may "
            "see content, `most_sensitive` to classify something derived from several records, "
            "`content_rank` and `ceiling_rank` for a rank, `TLP_ORDER` to enumerate the levels"
        ),
        incident=(
            "the exposure policy and the MCP context each kept a table of the four levels and ranked "
            "a value they did not recognise as TLP:WHITE, so assurance content whose level was "
            "misspelt or null was shown to a reader whose ceiling should have withheld it; two metric "
            "folds kept a third and fourth table and dropped such a value from the maximum"
        ),
        enumeration_probe=_TLP_LEVEL,
    ),
)

#: What each row's exemptions cost today. A ratchet in the spirit of the project's other shrink-only
#: registers: the number may fall and may never rise, so a twelfth reader cannot arrive quietly by
#: being added to a list.
_EXEMPTION_BUDGET: dict[str, int] = {
    "a markdown table — where one is, its rows, and the cells of a row": 4,
    "what a document's prose refers to — a markdown link and the file it addresses": 1,
    "what it means for a PUML line to declare an alias": 1,
    "the arrow form of a connection — a `###` section, or a standalone reference": 3,
    "which spelling of an artifact id is its identity — the short form, or the id with its slug": 2,
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


def _literals_deciding(
    path: Path, probe: re.Pattern[str], also_located_by: frozenset[str] = frozenset(),
    only_located_by: frozenset[str] = frozenset(),
) -> list[str]:
    """Literals this file hands to a locating call that spell the syntax itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    locating = only_located_by or _LOCATING_CALLS | also_located_by
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        literal = _first_string_argument(node)
        if literal is None or _called_name(node) not in locating:
            continue
        if probe.search(literal):
            found.add(literal)
    return sorted(found)


def _enumerations(path: Path, probe: re.Pattern[str]) -> list[str]:
    """Collection displays in this file naming two or more values the probe recognises."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        elements: list[ast.expr | None]
        match node:
            case ast.Tuple(elts=elts) | ast.List(elts=elts) | ast.Set(elts=elts):
                elements = list(elts)
            case ast.Dict(keys=keys):
                elements = list(keys)
            case _:
                continue
        named = [
            element.value for element in elements
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
            and probe.search(element.value)
        ]
        if len(named) >= 2:
            found.add(", ".join(named))
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
            found += _literals_deciding(
                path, reader.literal_probe, reader.also_located_by, reader.only_located_by,
            )
        if reader.enumeration_probe is not None:
            found += _enumerations(path, reader.enumeration_probe)
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
    assert (
        reader.reserved_names or reader.literal_probe is not None or reader.enumeration_probe is not None
    ), reader.syntax
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
        ("source", "decides"),
        [
            pytest.param('_TLP_ORDER = {"TLP:WHITE": 0, "TLP:GREEN": 1}', True, id="exposure-table"),
            pytest.param('order = ("TLP:WHITE", "TLP:GREEN", "TLP:AMBER", "TLP:RED")', True, id="metric-fold"),
            pytest.param('row.get("tlp", "TLP:AMBER")', False, id="a-stored-default"),
            pytest.param('tlp: str = "TLP:WHITE"', False, id="a-parameter-default"),
        ],
    )
    def test_a_table_of_tlp_levels_is_recognised_and_one_default_is_not(
        self, source: str, decides: bool, tmp_path: Path,
    ) -> None:
        module = tmp_path / "snippet.py"
        module.write_text(source, encoding="utf-8")

        assert bool(_enumerations(module, _TLP_LEVEL)) is decides, source

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
        ("source", "decides"),
        [
            pytest.param('stripped.split("|")[1:-1]', True, id="index-and-editor-cells"),
            pytest.param('stripped.startswith("|---") or stripped.startswith("| ---")', True, id="verifier-delimiter"),
            pytest.param('stripped.startswith("| Attribute")', True, id="verifier-header"),
            pytest.param('line.startswith("| ") and "](" not in line', True, id="matrix-row"),
            pytest.param(r'''re.match(r"^\s*\|", line)''', True, id="as-a-pattern"),
            pytest.param(r'''re.split(r"\|", line)''', True, id="as-an-escaped-pattern"),
            pytest.param('"|".join(cells)', False, id="writing-a-row"),
            pytest.param('value.replace("|", "/")', False, id="rewriting-a-label"),
            pytest.param('content.split(_TYPE_ALTERNATIVE)', False, id="a-named-separator"),
            pytest.param(r'''re.search(r"(up|down|left|right)", arrow)''', False, id="an-alternation"),
            pytest.param('artifact_id.split("---")', False, id="connection-id-separator"),
        ],
    )
    def test_a_table_reading_is_recognised_and_writing_one_is_not(self, source: str, decides: bool) -> None:
        """The first four are the readings this row replaced, verbatim."""
        tree = ast.parse(source)
        decisions = [
            literal
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (literal := _first_string_argument(node)) is not None
            and _called_name(node) in _LOCATING_CALLS
            and _TABLE_PIPE.search(literal)
        ]

        assert bool(decisions) is decides, source

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
