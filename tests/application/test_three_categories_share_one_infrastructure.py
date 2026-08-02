"""Models, diagrams and documents are one framework, not three that happen to coexist.

verifies: REQ@1712870400.HR7AGz

The requirement asserts three artifact categories — entities and their connections, PlantUML diagrams
referencing those entities, and documents with structured cross-references — and then makes a claim
*about* them: all three "share the same frontmatter schema, ID convention, and verification
infrastructure, providing a unified framework".

The obvious candidate for this marker was `test_verify_all_passes_clean_repo`, which writes a single
entity and passes `include_diagrams=False`. It evidences none of the three-way claim, and marking it
would have recorded coverage the product does not have — which is why this requirement stayed owed while
its feature was, in fact, built.

So the shape of the evidence has to match the shape of the claim, and the claim is a conjunction:

* **One verification infrastructure** — one `verify_all` call over a repository holding all three, with
  diagrams included, reporting on all three and finding no errors. Not three calls: three calls would
  demonstrate three verifiers working, which is the opposite of the claim.
* **One ID convention** — every id parses under `src/domain/artifact_id`, the module that defines the
  grammar once, and the prefixes differ while the *shape* does not.
* **One frontmatter base** — the same five fields are required of every category, checked through the
  same `check_required_fields` primitive against the same set, and each category carries a label field
  of its own on top.

Writing it turned up the one place the original text overreached: it claimed all three share "the same
frontmatter schema", and documents are keyed by `title` where entities and diagrams are keyed by `name`.
Collapsing those would rename a field in every document in every repository to satisfy a phrase, and
would make the vocabulary worse. The requirement was amended to state the sharing in the terms that are
true — one ID convention, one verification pass, one frontmatter *base* — and this file verifies the
amended text, including that the divergence it now admits to is really there.

Authored through the write tools rather than by writing files, for the reason the fixture workspace is:
if the write layer cannot produce all three, "the system shall support" them is not true, and a test
that hand-wrote the files would pass anyway.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ADR_BODY = (
    "## Context\n\nA document, so the third category is present.\n\n"
    "## Decision\n\nVerify all three through one call.\n\n"
    "## Consequences\n\nNone.\n"
)

#: The frontmatter base every *named* category carries. Stated rather than imported from
#: `ENTITY_REQUIRED`, because the point is what is common: a connection file is keyed by
#: `source-entity` rather than `artifact-id`, and the human label is `name` for entities and diagrams
#: but `title` for documents. Both divergences are deliberate and the requirement now says so — a
#: decision record has a title, an application component has a name — so what "one frontmatter base"
#: means is these five fields, required of every category and enforced by one primitive.
_SHARED_CORE = frozenset({"artifact-id", "artifact-type", "version", "status", "last-updated"})

#: The label field each category uses, which is the one place the base does *not* extend to. Asserted
#: rather than ignored: an amendment that says "the label differs by category" is only honest if
#: something checks that each category actually has one.
_LABEL_FIELD = {"entity": "name", "diagram": "name", "document": "title"}


@pytest.fixture()
def repo_with_all_three(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """One repository holding an entity, a connection, a diagram and a document.

    Built by `artifact_create_entity`, `artifact_add_connection`, `artifact_create_diagram` and
    `artifact_create_document` — the product's own authoring path for each category.
    """
    from src.infrastructure.mcp import mcp_artifact_server as write
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

    root = tmp_path / "engagements" / "ENG-THREE" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)
    where = str(root)

    def wrote(result: dict[str, object], what: str) -> str:
        assert result.get("wrote"), (what, result)
        identifier = result.get("artifact_id")
        assert isinstance(identifier, str), (what, result)
        return identifier

    source = wrote(
        write.artifact_create_entity(
            artifact_type="application-component", name="Three Source", dry_run=False, repo_root=where
        ),
        "source entity",
    )
    target = wrote(
        write.artifact_create_entity(
            artifact_type="application-component", name="Three Target", dry_run=False, repo_root=where
        ),
        "target entity",
    )
    connection = wrote(
        write.artifact_add_connection(
            source_entity=source,
            connection_type="archimate-serving",
            target_entity=target,
            dry_run=False,
            repo_root=where,
        ),
        "connection",
    )
    diagram = wrote(
        write.artifact_create_diagram(
            diagram_type="archimate-application",
            name="Three View",
            entity_ids=[source, target],
            dry_run=False,
            repo_root=where,
        ),
        "diagram",
    )
    document = wrote(
        write.artifact_create_document(
            doc_type="adr", title="Three Decision", body=_ADR_BODY, dry_run=False, repo_root=where
        ),
        "document",
    )
    return root, {
        "entity": source,
        "other_entity": target,
        "connection": connection,
        "diagram": diagram,
        "document": document,
    }


@pytest.mark.verifies("REQ@1712870400.HR7AGz")
def test_one_verify_call_covers_all_three_categories(
    repo_with_all_three: tuple[Path, dict[str, str]],
) -> None:
    """The load-bearing half of the claim: *one* verification infrastructure, not three.

    `include_diagrams=True` matters — the previous candidate for this marker passed False, which is how
    a test can walk a repository containing a diagram and evidence nothing about diagrams.
    """
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    root, _ids = repo_with_all_three
    with shared_artifact_index([root]) as index:
        verifier = ArtifactVerifier(
            ArtifactRegistry(index), catalogs=build_runtime_catalogs(build_module_registry())
        )
        results = verifier.verify_all(root, include_diagrams=True)

    errors = [issue for result in results for issue in result.errors]
    assert errors == [], [(i.code, i.message, i.location) for i in errors]

    # The verifier's own names for the four, read from its answer rather than guessed: it reports a
    # connection file as `connection`, not as the `outgoing` its filename and schema are keyed on.
    covered = {result.file_type for result in results}
    for category in ("entity", "connection", "diagram", "document"):
        assert category in covered, (category, sorted(covered))


@pytest.mark.verifies("REQ@1712870400.HR7AGz")
def test_every_category_uses_the_one_id_grammar(
    repo_with_all_three: tuple[Path, dict[str, str]],
) -> None:
    """One ID convention: the same parser accepts all of them, and the prefix is the only difference.

    A connection id is the composite of two entity ids, so it is decomposed to its endpoints rather
    than parsed whole — which is itself part of the convention rather than an exception to it.
    """
    from src.domain.artifact_id import parse_entity_id

    _root, ids = repo_with_all_three
    singular = [ids["entity"], ids["other_entity"], ids["diagram"], ids["document"]]

    prefixes = {parse_entity_id(identifier).prefix for identifier in singular}
    assert len(prefixes) == len(singular) - 1, prefixes  # the two entities share a prefix

    source, rest = ids["connection"].split("---", 1)
    target = rest.split("@@", 1)[0]
    for endpoint in (source, target):
        assert parse_entity_id(endpoint).prefix, endpoint


@pytest.mark.verifies("REQ@1712870400.HR7AGz")
def test_every_named_category_is_held_to_the_same_core_frontmatter(
    repo_with_all_three: tuple[Path, dict[str, str]],
) -> None:
    """One frontmatter base, asserted as "the same fields, enforced by the same primitive".

    Read off the authored files, so what is checked is what the write tools actually emit for each
    category rather than what a constant says they should.
    """
    from src.application.verification.artifact_verifier_parsing import parse_frontmatter, read_file
    from src.application.verification.artifact_verifier_rules import check_required_fields
    from src.application.verification.artifact_verifier_types import VerificationResult

    root, ids = repo_with_all_three
    for category, suffix in (("entity", ".md"), ("diagram", ".puml"), ("document", ".md")):
        path = _path_of(root, ids[category], suffix)
        result = VerificationResult(path=str(path), file_type=category)
        frontmatter = parse_frontmatter(read_file(path, result, str(path)) or "", result, str(path))
        assert frontmatter is not None, (category, result.issues)

        check_required_fields(frontmatter, _SHARED_CORE, result, str(path))

        assert result.issues == [], (category, [(i.code, i.message) for i in result.issues])
        label = _LABEL_FIELD[category]
        assert frontmatter.get(label), (category, label, sorted(frontmatter))


def _path_of(root: Path, artifact_id: str, suffix: str) -> Path:
    """The file an id names, found by the id being in the filename — which is the convention itself.

    The suffix is given rather than globbed: an entity's id also names its `.outgoing.md` sidecar, so
    `{id}.*` matches two files for one entity, and picking either by position would be an accident.
    """
    matches = [path for path in root.rglob(f"{artifact_id}{suffix}") if path.is_file()]
    assert len(matches) == 1, (artifact_id, suffix, matches)
    return matches[0]
