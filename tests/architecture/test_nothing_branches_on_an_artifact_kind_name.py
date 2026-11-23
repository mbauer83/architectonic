"""Nothing outside the kind table decides anything by comparing an artifact kind's name.

**What this stops.** A kind's facts are declared once, on its row in
`src/domain/repository/artifact_location.py`. Before that they were spelled where each was needed, as
a `match` or an `in (...)` over kind names: which kinds the verifier takes, which it verifies one
file at a time, which move the model generation. Every one was right on the day it was written and
had to be found again for the next kind, and the one in the bulk candidate store had no arm for an
icon at all — it dropped the file without anyone having decided that it should. A branch on a name is
a private copy of a fact; this test fails when a new one is written.

**How a branch is recognised.** By what is compared, not by which word: `"entity"` and `"document"`
are also search record types, viewpoint item kinds, binding subject kinds and a scratchpad note's
destination, and a rule that fired on the word reported 160 comparisons of which a tenth were about
an artifact kind. A value is a *kind name* when it comes from the table — the result of
`artifact_kind_at` or `model_file_kind`, the `.name` of a row, a name annotated with one of the
table's public types, or anything assigned from those. Comparing such a value with a string literal,
or matching it against one, is the branch.

**What is deliberately not one.** Asking a row for a fact (`declared.verification == "standalone"`
compares a fact, not a name). A table keyed by kind (`CHANGE_READERS[kind]`): that is a binding, it
has no arm to forget, and its completeness is held where it is declared. Naming a kind to ask about
it (`own_id_prefix("scratchpad")`) — a kind's own code knows which kind it is.

**What it cannot see.** A kind name that travels through a tuple, a container or an unannotated
parameter loses its mark, and a second `Literal` listing kind names is a declaration this does not
look for. It catches the branch written the obvious way, which is the way all of them were written.

**The register is shrink-only.** `_STILL_BRANCHING` lists the branches that remain, each with why it
is there and what removes it. A file may hold no more than its entry says, an entry whose branches
have gone must go too, and the total may fall and never rise.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT, SRC, TOOLS, python_sources

#: The table and its self-check: the only modules that may know a kind by its name.
_OWNERS = frozenset({
    Path("src/domain/repository/artifact_location.py"),
    Path("src/domain/repository/artifact_kind_consistency.py"),
})

#: The table's public types of kind name, and the verifier's alias of one of them.
_KIND_NAME_TYPES = frozenset({"ArtifactKindName", "VerifiedArtifactKindName", "VerificationFileType"})
#: The table's readings that answer with a kind name.
_KIND_NAME_READINGS = frozenset({"artifact_kind_at", "model_file_kind"})
#: The table's row type, its readings that answer with a row, and the rows themselves.
_ROW_TYPE = "KindDeclaration"
_ROW_READINGS = frozenset({"artifact_kind_declared_at", "artifact_kind"})
_ROW_COLLECTIONS = frozenset({"ARTIFACT_KINDS"})
_NAME_COLLECTIONS = frozenset({"ARTIFACT_KIND_NAMES"})


@dataclass(frozen=True)
class Remaining:
    """The kind-name branches one module still holds."""

    branches: int
    #: Why they are there — what the branch decides that no row states yet.
    why: str
    #: The stage of the kind consolidation that removes them, or why none does.
    until: str


_MODEL_FILES = (
    "stays: entities and connections keep their own index structures, and a walk of a model root "
    "has to tell an entity's file from the outgoing file beside it; `model_file_kind` is the one "
    "reading of that, and the comparison only says which of the two the walker wants"
)

_STILL_BRANCHING: dict[Path, Remaining] = {
    Path("src/application/verification/artifact_verifier.py"): Remaining(
        branches=1,
        why=(
            "`verify_connection_file` asks whether the file it was given is an outgoing file before "
            "reading it as one"
        ),
        until=_MODEL_FILES,
    ),
    Path("src/infrastructure/mcp/artifact_mcp/bulk/candidate_inventory.py"): Remaining(
        branches=4,
        why=(
            "the bulk inventory files a changed path under the model inventory's one list per kind "
            "(entities, connections, diagrams by notation), and expands a changed entity to what "
            "refers to it"
        ),
        until=(
            "stays while the model inventory keeps one list per kind verified with the model, which the "
            "bulk inventory has to fill as the full one does; the entity test " + _MODEL_FILES
        ),
    ),
    Path("src/infrastructure/write/artifact_write/candidate_state.py"): Remaining(
        branches=2,
        why=(
            "the staging overlay keeps staged records of four kinds in four dictionaries and absorbs "
            "a touched path into the one for its kind; a verified kind it keeps none of is refused"
        ),
        until=(
            "stage 4 (the record lane): a lane kind's staged records are held by kind, so the "
            "overlay has no arm per kind; the entity test " + _MODEL_FILES
        ),
    ),
    Path("src/infrastructure/rest/routers/sync/changes.py"): Remaining(
        branches=1,
        why=(
            "the save dialog merges an entity's outgoing file into its entity's row, under the "
            "heading `connections`"
        ),
        until="stage 3 (the dialog lists every changed path by its class, derived from the table)",
    ),
    Path("src/infrastructure/artifact_index/_service_scan.py"): Remaining(
        branches=2,
        why=(
            "the icon scan keeps only the files the layout reads as icons, and the entity scan skips "
            "outgoing files"
        ),
        until="stage 4 (the record lane scans a lane kind from its row); the entity scan " + _MODEL_FILES,
    ),
    Path("src/infrastructure/write/artifact_write/promote_execute.py"): Remaining(
        branches=1,
        why="promotion picks the diagrams out of the files it copied, to name the enterprise icons in them",
        until=(
            "stays until promotion takes its kinds from the rows that declare themselves promotable "
            "(the tier policy, which has no reader in stage 1 and so no field yet)"
        ),
    ),
    Path("src/infrastructure/write/artifact_write/cascade_delete.py"): Remaining(
        branches=1, why="a cascade delete collects the outgoing files under a model root", until=_MODEL_FILES,
    ),
    Path("src/application/verification/_verifier_inventory.py"): Remaining(
        branches=1, why="the verifier's inventory lists a model root's entity files", until=_MODEL_FILES,
    ),
}

#: The register's total. It may fall and may never rise: lower it when a branch goes.
_BUDGET = 13


# ── The detector ──────────────────────────────────────────────────────────────


def _names_a_kind_type(annotation: ast.expr | None, types: frozenset[str]) -> bool:
    if annotation is None:
        return False
    source = ast.unparse(annotation)
    return any(name in source for name in types)


def _called(node: ast.expr) -> str:
    if not isinstance(node, ast.Call):
        return ""
    target = node.func
    return target.attr if isinstance(target, ast.Attribute) else target.id if isinstance(target, ast.Name) else ""


def _own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Every node of *scope* that is not inside a function nested in it."""
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            pending.extend(ast.iter_child_nodes(node))


def functions_answering_a_kind_name(trees: list[ast.Module]) -> frozenset[str]:
    """Functions anywhere whose declared return is a kind name: calling one yields a kind name."""
    return frozenset(
        node.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and _names_a_kind_type(node.returns, _KIND_NAME_TYPES)
    )


class _Scope:
    """Which names in one function (or at module level) hold a kind name, and which hold a row."""

    def __init__(self, scope: ast.AST, readings: frozenset[str]) -> None:
        self._readings = _KIND_NAME_READINGS | readings
        self.kind_names: set[str] = set()
        self.rows: set[str] = set()
        self._nodes = list(_own_nodes(scope))
        if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
            for argument in (*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs):
                self._annotated(argument.arg, argument.annotation)
        # Twice: an assignment may be read before the walk reaches the one it depends on.
        for _ in range(2):
            for node in self._nodes:
                self._learn(node)

    def _annotated(self, name: str, annotation: ast.expr | None) -> None:
        if _names_a_kind_type(annotation, _KIND_NAME_TYPES):
            self.kind_names.add(name)
        elif _names_a_kind_type(annotation, frozenset({_ROW_TYPE})):
            self.rows.add(name)

    def _bind(self, target: ast.expr, value: ast.expr) -> None:
        if not isinstance(target, ast.Name):
            return
        if self.is_kind_name(value):
            self.kind_names.add(target.id)
        elif self.is_row(value):
            self.rows.add(target.id)

    def _learn(self, node: ast.AST) -> None:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            self._annotated(node.target.id, node.annotation)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self._bind(target, node.value)
        elif isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value is not None:
            self._bind(node.target, node.value)
        elif isinstance(node, ast.For | ast.comprehension) and isinstance(node.target, ast.Name):
            collection = node.iter.id if isinstance(node.iter, ast.Name) else ""
            if collection in _ROW_COLLECTIONS:
                self.rows.add(node.target.id)
            elif collection in _NAME_COLLECTIONS:
                self.kind_names.add(node.target.id)
        elif isinstance(node, ast.Match) and self.is_kind_name(node.subject):
            self.kind_names.update(
                pattern.name
                for case in node.cases
                for pattern in ast.walk(case.pattern)
                if isinstance(pattern, ast.MatchAs) and pattern.name is not None
            )

    def is_row(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.rows
        return _called(node) in _ROW_READINGS

    def is_kind_name(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.kind_names
        if isinstance(node, ast.NamedExpr):
            return self.is_kind_name(node.value)
        if isinstance(node, ast.BoolOp):
            return any(self.is_kind_name(value) for value in node.values)
        if isinstance(node, ast.IfExp):
            return self.is_kind_name(node.body) or self.is_kind_name(node.orelse)
        if isinstance(node, ast.Attribute):
            return node.attr == "name" and self.is_row(node.value)
        return _called(node) in self._readings

    def branches(self) -> Iterator[ast.AST]:
        for node in self._nodes:
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                if any(self.is_kind_name(o) for o in operands) and any(_spells_a_name(o) for o in operands):
                    yield node
            elif isinstance(node, ast.Match) and self.is_kind_name(node.subject):
                if any(_spells_a_name(p.value) for c in node.cases for p in ast.walk(c.pattern)
                       if isinstance(p, ast.MatchValue)):
                    yield node


def _spells_a_name(node: ast.expr) -> bool:
    """A string literal, or a tuple, list or set of them."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    return isinstance(node, ast.Tuple | ast.List | ast.Set) and any(_spells_a_name(item) for item in node.elts)


def kind_name_branches(tree: ast.Module, readings: frozenset[str] = frozenset()) -> list[int]:
    """The line of every comparison or `match` in *tree* that decides by a kind's name."""
    scopes = [tree, *(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))]
    return sorted(
        getattr(branch, "lineno", 0) for scope in scopes for branch in _Scope(scope, readings).branches()
    )


def _branches_by_module() -> dict[Path, list[int]]:
    sources = {path.relative_to(REPO_ROOT): path for path in python_sources(SRC, TOOLS)}
    trees = {relative: ast.parse(path.read_text(encoding="utf-8")) for relative, path in sources.items()}
    readings = functions_answering_a_kind_name(list(trees.values()))
    return {
        relative: lines
        for relative, tree in trees.items()
        if relative not in _OWNERS and (lines := kind_name_branches(tree, readings))
    }


# ── The gate ──────────────────────────────────────────────────────────────────


def test_the_owners_are_where_this_test_expects_them() -> None:
    """Without this, moving the table would make the gate vacuously satisfied."""
    for owner in _OWNERS:
        assert (REPO_ROOT / owner).is_file(), f"{owner} owns the kind table and is not there"


def test_nothing_outside_the_table_branches_on_a_kind_name() -> None:
    over = {
        str(module): f"{len(lines)} found at lines {lines}, {allowed} registered"
        for module, lines in _branches_by_module().items()
        if len(lines) > (allowed := _STILL_BRANCHING[module].branches if module in _STILL_BRANCHING else 0)
    }

    assert over == {}, (
        "these decide something by comparing an artifact kind's name. That is a private copy of a "
        "fact the kind's row should state: ask the row (`artifact_kind_declared_at(path)`, "
        "`artifact_kind(name)`) for the fact, and add the fact to `KindDeclaration` in "
        "`src/domain/repository/artifact_location.py` if it is not there yet. A new kind must not "
        f"need this code found again. {over}"
    )


def test_the_register_holds_no_more_than_is_still_there() -> None:
    """Shrink-only from the other side: an allowance for a branch that has gone admits the next one."""
    found = {module: len(lines) for module, lines in _branches_by_module().items()}
    stale = {
        str(module): f"{entry.branches} registered, {found.get(module, 0)} found"
        for module, entry in _STILL_BRANCHING.items()
        if found.get(module, 0) < entry.branches
    }

    assert stale == {}, f"lower or remove these entries, and `_BUDGET` with them: {stale}"


def test_the_register_does_not_grow() -> None:
    total = sum(entry.branches for entry in _STILL_BRANCHING.values())

    assert total <= _BUDGET, (
        f"{total} registered kind-name branches against a budget of {_BUDGET}. Convert the branch "
        "instead of registering it; lower the budget when one goes."
    )


@pytest.mark.parametrize("module", sorted(_STILL_BRANCHING), ids=str)
def test_every_registered_branch_says_why_and_until_when(module: Path) -> None:
    entry = _STILL_BRANCHING[module]

    assert len(entry.why) > 40 and len(entry.until) > 40, module
    assert entry.until.startswith(("stage ", "stays")), (
        f"{module}: say which stage of the consolidation removes the branch, or why none does"
    )


class TestTheDetectorCatchesWhatItClaims:
    """Applied to snippets, so the guard is tested rather than trusted — each is a branch that existed."""

    @pytest.mark.parametrize(
        "branch",
        [
            pytest.param(
                'match artifact_kind_at(rel):\n    case "scratchpad" | None:\n        pass', id="match-on-the-reading"
            ),
            pytest.param('ok = artifact_kind_at(rel) in ("document", "icon")', id="membership-in-a-tuple-of-names"),
            pytest.param('ok = model_file_kind(path) != "entity"', id="the-model-file-reading"),
            pytest.param('kind = artifact_kind_at(rel)\nok = kind == "connection"', id="through-an-assignment"),
            pytest.param(
                'def f(kind: ArtifactKindName) -> bool:\n    return kind != "scratchpad"', id="an-annotated-parameter"
            ),
            pytest.param(
                'def f(file_type: VerificationFileType | None, p):\n'
                '    inferred = file_type or g(p)\n'
                '    match inferred:\n        case "entity":\n            pass',
                id="through-an-or",
            ),
            pytest.param('ok = artifact_kind_declared_at(rel).name == "icon"', id="the-name-of-a-row"),
            pytest.param('ok = [k for k in ARTIFACT_KINDS if k.name == "icon"]', id="a-row-from-the-table"),
            pytest.param(
                'if (kind := artifact_kind_at(rel)) is not None and kind == "icon":\n    pass', id="through-a-walrus"
            ),
        ],
    )
    def test_a_branch_on_a_kind_name_is_recognised(self, branch: str) -> None:
        assert kind_name_branches(ast.parse(branch)), branch

    def test_a_function_declared_to_answer_a_kind_name_marks_its_callers(self) -> None:
        tree = ast.parse(
            'def kind_for(path) -> ArtifactKindName | None:\n    return artifact_kind_at(path)\n\n'
            'def use(path):\n    return kind_for(path) == "icon"\n'
        )

        assert kind_name_branches(tree, functions_answering_a_kind_name([tree])) == [5]

    @pytest.mark.parametrize(
        "not_a_branch",
        [
            pytest.param('ok = artifact_kind_declared_at(rel).verification == "standalone"', id="asking-a-fact"),
            pytest.param("reader = CHANGE_READERS[artifact_kind_at(rel)]", id="a-table-keyed-by-kind"),
            pytest.param('prefix = own_id_prefix("scratchpad")', id="naming-a-kind-to-ask-about-it"),
            pytest.param("ok = artifact_kind_at(rel) is None", id="no-kind-at-all"),
            pytest.param('ok = hit.record_type == "entity"', id="a-search-record-type"),
            pytest.param('ok = note.destination == "document"', id="a-note-destination"),
            pytest.param('kind = "entity"\nok = kind == "entity"', id="a-name-that-is-not-from-the-table"),
            pytest.param(
                'def f(kind: ArtifactKindName):\n    pass\n\ndef g(kind: str):\n    return kind == "icon"',
                id="the-same-name-in-another-function",
            ),
        ],
    )
    def test_what_is_not_a_branch_on_a_kind_name_is_left_alone(self, not_a_branch: str) -> None:
        assert kind_name_branches(ast.parse(not_a_branch)) == [], not_a_branch
