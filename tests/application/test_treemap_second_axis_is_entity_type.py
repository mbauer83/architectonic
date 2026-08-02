"""The treemap's second grouping axis is the entity type, under the name `subdomain`.

verifies: REQ@1777372175.eFz3z9

The requirement asks for a treemap "grouped by ArchiMate domain and entity-type, size by total number
of connections". `UNVERIFIED_REQUIREMENTS` recorded it as a partial implementation needing a decision:
"The second axis is subdomain", implying a different axis and so a product change or an amendment.

It is the same axis under a different name, and that is structural rather than a coincidence of the
current content:

* `derive_domain` reads an entity's domain and subdomain off its path — `model/<parts[0]>/<parts[1]>/`.
* An entity is written to `repo_root/projects/<group>/model/<*info.hierarchy>/<id>.md`.
* Every ontology loader builds that hierarchy as `declared_domain_segments + (artifact_type,)`, so the
  leaf directory *is* the artifact type; the YAML never spells it.

So `parts[1] == artifact_type` for every entity type whose declared hierarchy is one segment deep, which
is every entity type in every shipped ontology. That last clause is the real content of this file: the
equivalence is not a law of the system but a property of the type catalogue, and a three-segment
hierarchy would silently turn the treemap's second axis into something that is *not* the entity type
while every test that only looked at today's content kept passing. So the invariant is asserted over the
**declared types**, not over the entities that happen to exist.

The frontend half — that the treemap actually groups on `domain` then `subdomain`, and sizes by
connection total — is `EntitiesTreemap`'s own unit test, which carries the same marker.
"""

from __future__ import annotations

import pytest


def _entity_types() -> dict[str, object]:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    catalogs = build_runtime_catalogs(build_module_registry())
    return dict(catalogs.ontology.all_entity_types())


@pytest.mark.verifies("REQ@1777372175.eFz3z9")
def test_every_declared_entity_type_files_under_a_directory_named_after_itself() -> None:
    """`hierarchy[-1] == artifact_type`, which is what makes the leaf directory the entity type.

    By construction in each loader, and asserted anyway: the construction is three lines in three
    separate ontology packages, and a fourth ontology that spelled its leaf by hand would break the
    treemap's second axis without breaking anything that looks like a treemap.
    """
    mismatched = {
        name: info.hierarchy
        for name, info in _entity_types().items()
        if not info.hierarchy or info.hierarchy[-1] != name
    }
    assert mismatched == {}, mismatched


@pytest.mark.verifies("REQ@1777372175.eFz3z9")
def test_the_type_directory_is_the_second_path_segment_so_subdomain_is_the_entity_type() -> None:
    """The clause that makes "subdomain" and "entity-type" the same axis rather than two.

    `derive_domain` takes the subdomain from `parts[1]` specifically, so the equivalence holds only
    while a hierarchy is `(domain, type)`. A type filed at `model/technology/infrastructure/node/`
    would report `infrastructure` as its subdomain, and the treemap would group by something that is
    neither the domain nor the type — silently, and only for that type.
    """
    deeper = {
        name: info.hierarchy for name, info in _entity_types().items() if len(info.hierarchy) != 2
    }
    assert deeper == {}, (
        "these entity types are filed deeper than model/<domain>/<type>/, so their `subdomain` is no "
        f"longer their entity type and the treemap's second axis stops meaning what it says: {deeper}"
    )


@pytest.mark.verifies("REQ@1777372175.eFz3z9")
def test_an_authored_entity_reports_its_own_type_as_its_subdomain(tmp_path) -> None:
    """The two facts above, met end to end: write an entity, read it back, compare the two fields.

    Through the write tool and the index rather than through `derive_domain` directly, because what
    the treemap consumes is `EntitySummary.subdomain` as the API serves it, and the path in between is
    where a filing change would actually land.
    """
    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.mcp import mcp_artifact_server as write
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults

    root = tmp_path / "engagements" / "ENG-TREEMAP" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)

    created = write.artifact_create_entity(
        artifact_type="application-component",
        name="Treemap Axis Probe",
        dry_run=False,
        repo_root=str(root),
    )
    assert created.get("wrote"), created

    with shared_artifact_index([root]) as index:
        repository = ArtifactRepository(index)
        entities = [e for e in repository.list_entities() if e.artifact_id == created["artifact_id"]]

    assert len(entities) == 1, created["artifact_id"]
    entity = entities[0]
    assert entity.subdomain == entity.artifact_type == "application-component", (
        entity.domain,
        entity.subdomain,
        entity.artifact_type,
    )
    assert entity.domain == "application", entity.domain
