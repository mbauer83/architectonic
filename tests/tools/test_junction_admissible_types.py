"""A junction may only join a relationship its participants could have held directly.

The type-level table cannot say this. `connections.yaml` admits all eleven junction-capable types
between any element and a junction, in both directions, because whether a given one is admissible
depends on which *other* elements that junction instance joins — an instance property, not a type
property. So the table let `function --assignment--> J --assignment--> function` through while
`function --assignment--> function` is refused, and the model asserted by proxy what it may not
assert directly. Now that derivation passes through junctions (`RJ3`), that assertion becomes a
derived relationship the ontology forbids.

Two rules, both reported against the file that declares the offending leg:

* **E128** — every leg of one junction carries the same type. A junction splits or joins *one*
  relationship; legs of different types are a modelling error, and derivation already refuses to
  compose them, silently.
* **E129** — the carried type is permitted between every upstream and every downstream participant.
  That intersection is what the junction stands for.

These run through the real verifier over a real index, because the legs of a junction live in as many
files as it has participants and the rule is only meaningful when it can see all of them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index

_ASSIGNMENT = "archimate-assignment"
_TRIGGERING = "archimate-triggering"
_REALIZATION = "archimate-realization"


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


@lru_cache(maxsize=1)
def _entity_types() -> dict:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return {str(k): v for k, v in build_module_registry().all_entity_types().items()}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity_path(repo: Path, artifact_id: str, artifact_type: str) -> Path:
    hierarchy = _entity_types()[artifact_type].hierarchy
    return repo / "model" / Path(*hierarchy) / f"{artifact_id}.md"


def _write_entity(repo: Path, artifact_id: str, artifact_type: str) -> None:
    prefix, rand = artifact_id.split("@")[0], artifact_id.split(".")[1]
    _write(
        _entity_path(repo, artifact_id, artifact_type),
        f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{artifact_id}"
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---

<!-- §content -->

## {artifact_id}

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{artifact_id}"
alias: {prefix}_{rand}
```
""",
    )


def _write_outgoing(repo: Path, source: str, artifact_type: str, legs: list[tuple[str, str]]) -> Path:
    sections = "\n".join(f"### {conn_type} → {target}\n" for conn_type, target in legs)
    path = _entity_path(repo, source, artifact_type).with_suffix("").with_suffix(".outgoing.md")
    _write(
        path,
        f"""\
---
source-entity: {source}
version: 0.1.0
status: draft
last-updated: '2026-04-17'
---

<!-- §connections -->

{sections}
""",
    )
    return path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    return root


_JUNCTION = "JNA@1000000000.JunAaa.junction"
_ROLE = "ROL@1000000001.RolBbb.role"
_FUNCTION_A = "FNC@1000000002.FncCcc.function-a"
_FUNCTION_B = "FNC@1000000003.FncDdd.function-b"
_REQUIREMENT = "REQ@1000000004.ReqEee.requirement"


def _scenario(
    repo: Path,
    *,
    in_leg: tuple[str, str, str],
    out_legs: list[tuple[str, str]],
    participants: list[tuple[str, str]],
) -> None:
    """Author a junction, its participants, one upstream leg and the junction's own out-legs."""
    _write_entity(repo, _JUNCTION, "and-junction")
    for artifact_id, artifact_type in participants:
        _write_entity(repo, artifact_id, artifact_type)
    source_id, source_type, conn_type = in_leg
    _write_outgoing(repo, source_id, source_type, [(conn_type, _JUNCTION)])
    _write_outgoing(repo, _JUNCTION, "and-junction", out_legs)


def _verify(repo: Path, path: Path):
    registry = ArtifactRegistry(shared_artifact_index(repo))
    return ArtifactVerifier(registry, catalogs=_catalogs()).verify_outgoing_file(path)


def _codes(result) -> list[str]:
    return [issue.code for issue in result.issues]


# ── E129: the intersection of what the participants permit ────────────────────


def test_a_junction_joining_a_permitted_relationship_passes(repo: Path) -> None:
    """A role assigned to a function through a junction: permitted directly, so permitted joined."""
    _scenario(
        repo,
        in_leg=(_ROLE, "role", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_A)],
        participants=[(_ROLE, "role"), (_FUNCTION_A, "function")],
    )

    result = _verify(repo, _entity_path(repo, _ROLE, "role").with_suffix("").with_suffix(".outgoing.md"))

    assert result.valid, [issue.message for issue in result.issues]


def test_a_junction_may_not_join_what_the_participants_could_not_hold(repo: Path) -> None:
    """The hole this closes: assignment is permitted to and from a junction, but not function→function."""
    _scenario(
        repo,
        in_leg=(_FUNCTION_A, "function", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_B)],
        participants=[(_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )

    result = _verify(repo, _entity_path(repo, _FUNCTION_A, "function").with_suffix("").with_suffix(".outgoing.md"))

    assert "E129" in _codes(result)
    (issue,) = [i for i in result.issues if i.code == "E129"]
    assert _JUNCTION in issue.message
    assert _FUNCTION_A in issue.message and _FUNCTION_B in issue.message
    assert "assignment" in issue.message


def test_the_junction_s_own_file_is_told_too(repo: Path) -> None:
    """Both files declare a leg of the same illegal relationship, so both are wrong."""
    _scenario(
        repo,
        in_leg=(_FUNCTION_A, "function", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_B)],
        participants=[(_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )

    result = _verify(
        repo, _entity_path(repo, _JUNCTION, "and-junction").with_suffix("").with_suffix(".outgoing.md")
    )

    assert "E129" in _codes(result)


def test_each_downstream_participant_is_judged_separately(repo: Path) -> None:
    """The admissible set is an intersection, so one bad participant is enough — and only that one
    is named. A role may be assigned to a function but not to a requirement."""
    _scenario(
        repo,
        in_leg=(_ROLE, "role", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_A), (_ASSIGNMENT, _REQUIREMENT)],
        participants=[(_ROLE, "role"), (_FUNCTION_A, "function"), (_REQUIREMENT, "requirement")],
    )

    result = _verify(repo, _entity_path(repo, _ROLE, "role").with_suffix("").with_suffix(".outgoing.md"))

    assert _codes(result).count("E129") == 1
    assert _REQUIREMENT in next(i.message for i in result.issues if i.code == "E129")


def test_a_participant_is_not_told_about_another_participant_s_pair(repo: Path) -> None:
    """Locality: each file answers for the leg it declares, not for the junction's cross-product."""
    _scenario(
        repo,
        in_leg=(_ROLE, "role", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_A)],
        participants=[(_ROLE, "role"), (_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )
    offending = _write_outgoing(repo, _FUNCTION_B, "function", [(_ASSIGNMENT, _JUNCTION)])

    clean = _verify(repo, _entity_path(repo, _ROLE, "role").with_suffix("").with_suffix(".outgoing.md"))

    assert "E129" not in _codes(clean)
    assert "E129" in _codes(_verify(repo, offending))


def test_a_direct_relationship_between_the_same_types_is_still_judged_on_its_own(repo: Path) -> None:
    """The junction rule adds a check; it does not replace E126 or fire without a junction."""
    _write_entity(repo, _FUNCTION_A, "function")
    _write_entity(repo, _FUNCTION_B, "function")
    path = _write_outgoing(repo, _FUNCTION_A, "function", [(_ASSIGNMENT, _FUNCTION_B)])

    result = _verify(repo, path)

    assert "E126" in _codes(result)
    assert "E129" not in _codes(result)


# ── E128: one junction, one relationship type ─────────────────────────────────


def test_legs_of_different_types_are_refused(repo: Path) -> None:
    _scenario(
        repo,
        in_leg=(_FUNCTION_A, "function", _TRIGGERING),
        out_legs=[(_REALIZATION, _FUNCTION_B)],
        participants=[(_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )

    result = _verify(repo, _entity_path(repo, _FUNCTION_A, "function").with_suffix("").with_suffix(".outgoing.md"))

    assert "E128" in _codes(result)
    (issue,) = [i for i in result.issues if i.code == "E128"]
    assert _TRIGGERING in issue.message and _REALIZATION in issue.message


def test_mismatched_legs_do_not_also_produce_an_admissibility_error(repo: Path) -> None:
    """With no single type agreed there is no type left to ask about — one diagnosis, not two."""
    _scenario(
        repo,
        in_leg=(_FUNCTION_A, "function", _ASSIGNMENT),
        out_legs=[(_REALIZATION, _FUNCTION_B)],
        participants=[(_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )

    result = _verify(repo, _entity_path(repo, _FUNCTION_A, "function").with_suffix("").with_suffix(".outgoing.md"))

    assert "E128" in _codes(result)
    assert "E129" not in _codes(result)


def test_agreeing_legs_are_not_reported_twice_because_the_leg_is_indexed(repo: Path) -> None:
    """The declaration under verification is usually already in the index; counting it again as a
    second, differing leg would make every committed junction fail."""
    _scenario(
        repo,
        in_leg=(_ROLE, "role", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_A)],
        participants=[(_ROLE, "role"), (_FUNCTION_A, "function")],
    )

    junction_file = _entity_path(repo, _JUNCTION, "and-junction").with_suffix("").with_suffix(".outgoing.md")

    assert _verify(repo, junction_file).valid


def test_a_second_upstream_participant_is_judged_against_every_downstream_one(repo: Path) -> None:
    """A join: both upstream legs have to be admissible against the downstream participant."""
    _scenario(
        repo,
        in_leg=(_ROLE, "role", _ASSIGNMENT),
        out_legs=[(_ASSIGNMENT, _FUNCTION_A)],
        participants=[(_ROLE, "role"), (_FUNCTION_A, "function"), (_FUNCTION_B, "function")],
    )
    second = _write_outgoing(repo, _FUNCTION_B, "function", [(_ASSIGNMENT, _JUNCTION)])

    result = _verify(repo, second)

    assert "E129" in _codes(result)
    assert _FUNCTION_A in next(i.message for i in result.issues if i.code == "E129")


def test_the_live_self_model_s_junctions_are_admissible() -> None:
    """The rule is an authoring constraint, so the repository it governs has to satisfy it."""
    repo_root = Path("engagements/ENG-ARCH-REPO/architecture-repository").resolve()
    if not repo_root.exists():  # pragma: no cover - the self-model is present in this checkout
        pytest.skip("self-model repository not present")
    registry = ArtifactRegistry(shared_artifact_index(repo_root))
    verifier = ArtifactVerifier(registry, catalogs=_catalogs())
    junction_types = _catalogs().ontology.entity_types_with_class("junction")

    offences: list[str] = []
    for artifact_id in sorted(registry.entity_ids()):
        entity = registry.get_entity(artifact_id)
        if entity is None or entity.artifact_type not in junction_types:
            continue
        for connection in registry.find_connections_for(artifact_id, direction="any"):
            result = verifier.verify_outgoing_file(connection.path)
            offences.extend(
                f"{i.code}: {i.message}" for i in result.issues if i.code in {"E128", "E129"}
            )

    assert offences == [], offences


# ── The write path refuses what the verifier reports ──────────────────────────


def _plant(repo: Path) -> None:
    for artifact_id, artifact_type in (
        (_JUNCTION, "and-junction"),
        (_ROLE, "role"),
        (_FUNCTION_A, "function"),
        (_FUNCTION_B, "function"),
    ):
        _write_entity(repo, artifact_id, artifact_type)


def test_the_write_path_refuses_an_inadmissible_leg(repo: Path) -> None:
    """Authoring is where this belongs: the junction already assigns to a function, so a function
    may not join it — that would assert function→function assignment by proxy."""
    from src.infrastructure.mcp import mcp_artifact_server as write_tools  # noqa: PLC0415

    _plant(repo)
    _write_outgoing(repo, _JUNCTION, "and-junction", [(_ASSIGNMENT, _FUNCTION_B)])

    with pytest.raises(ValueError, match="not permitted"):
        write_tools.artifact_add_connection(
            source_entity=_FUNCTION_A,
            connection_type=_ASSIGNMENT,
            target_entity=_JUNCTION,
            description="joins a junction it may not join",
            repo_root=str(repo),
            dry_run=False,
        )


def test_the_write_path_refuses_a_leg_of_a_different_type(repo: Path) -> None:
    from src.infrastructure.mcp import mcp_artifact_server as write_tools  # noqa: PLC0415

    _plant(repo)
    _write_outgoing(repo, _ROLE, "role", [(_ASSIGNMENT, _JUNCTION)])

    with pytest.raises(ValueError, match="same type"):
        write_tools.artifact_add_connection(
            source_entity=_JUNCTION,
            connection_type=_TRIGGERING,
            target_entity=_FUNCTION_A,
            description="a second relationship type on one junction",
            repo_root=str(repo),
            dry_run=False,
        )


def test_the_write_path_still_accepts_an_admissible_leg(repo: Path) -> None:
    from src.infrastructure.mcp import mcp_artifact_server as write_tools  # noqa: PLC0415

    _plant(repo)
    _write_outgoing(repo, _JUNCTION, "and-junction", [(_ASSIGNMENT, _FUNCTION_A)])

    result = write_tools.artifact_add_connection(
        source_entity=_ROLE,
        connection_type=_ASSIGNMENT,
        target_entity=_JUNCTION,
        description="a role assigned to a function through a junction",
        repo_root=str(repo),
        dry_run=False,
    )

    assert result.get("wrote") is True, result
