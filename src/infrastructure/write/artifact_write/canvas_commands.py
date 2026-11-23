"""Apply the model commands of a canvas save and the diagram replacement in one staged write."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from src.application.artifacts.repository import ArtifactRepository
from src.application.repo_path_helpers import rendered_path_for
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import connection_id_as_written, parse_entity_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier

from .batch_transaction import commit_staged_repo, create_staging_repo, location_in_live, path_in_live, text_in_live
from .boundary import assert_engagement_write_root
from .connection import add_connection
from .connection_edit import edit_connection
from .entity import create_entity
from .entity_delete import delete_entity
from .entity_edit import edit_entity
from .staged_state import StagedStore
from .types import WriteResult


@dataclass(frozen=True)
class CreateElement:
    op: Literal["model.element.create"]
    artifact_id: str
    name: str
    group: str
    artifact_type: str | None = None
    summary: str = ""
    specializations: tuple[str, ...] = ()
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RenameElement:
    op: Literal["model.element.rename"]
    artifact_id: str
    name: str


@dataclass(frozen=True)
class DeleteElement:
    op: Literal["model.element.delete"]
    artifact_id: str


@dataclass(frozen=True)
class ConnectElements:
    op: Literal["model.relation.create", "model.relation.edit"]
    artifact_id: str
    description: str = ""
    src_multiplicity: str = ""
    tgt_multiplicity: str = ""


type CanvasCommand = CreateElement | RenameElement | DeleteElement | ConnectElements
type SaveDiagram = Callable[[Path, StagedStore, ArtifactVerifier, Callable[[Path], None], bool], WriteResult]


def canvas_save(
    commands: Sequence[CanvasCommand], root: Path, catalogs: RuntimeCatalogs, dry_run: bool,
    live_repo: ArtifactRepository, save_diagram: SaveDiagram, changed: Callable[[list[Path]], None],
) -> WriteResult:
    assert_engagement_write_root(root)
    staging, staged = create_staging_repo(root)
    touched: set[Path] = set()
    live = shared_artifact_index(live_repo.repo_mounts)

    def context() -> tuple[StagedStore, ArtifactRegistry, ArtifactVerifier]:
        store = StagedStore(live=live, live_root=root, staged_root=staged, touched_paths=touched,
                               domain_names=catalogs.ontology.known_domain_names())
        registry = ArtifactRegistry(store)
        return store, registry, build_artifact_verifier(registry, catalogs=catalogs)

    def require(result: WriteResult) -> None:
        if not result.wrote or result.error_messages:
            raise ValueError(" ".join(result.error_messages or result.warnings) or "The canvas change was refused")

    try:
        for command in commands:
            store, registry, verifier = context()
            # Model mutations can only change files inside this transaction. Enterprise
            # records remain available as diagram members and relationship targets.
            owner = (connection_id_as_written(command.artifact_id)[0]
                     if isinstance(command, ConnectElements) else command.artifact_id)
            if store.scope_of_entity(owner) == "enterprise":
                raise ValueError(f"The enterprise element {owner} is read-only here")
            match command:
                case CreateElement():
                    kind = catalogs.ontology.entity_type_prefixes().get(parse_entity_id(command.artifact_id).prefix)
                    if (kind is None or command.artifact_type not in (None, kind)
                            or registry.get_entity(command.artifact_id) is not None):
                        raise ValueError(f"Invalid or duplicate proposed element {command.artifact_id}")
                    result = create_entity(
                        repo_root=staged, verifier=verifier, clear_repo_caches=touched.add, artifact_type=kind,
                        name=command.name, summary=command.summary, notes=None, properties=command.attributes,
                        group=command.group, specializations=command.specializations, artifact_id=command.artifact_id,
                        version="0.1.0", status="draft", last_updated=None, dry_run=False,
                    )
                    require(result)
                    if result.artifact_id != command.artifact_id:
                        raise ValueError("The proposed element identity is already in use")
                case RenameElement():
                    require(edit_entity(
                        repo_root=staged, registry=registry, verifier=verifier, clear_repo_caches=touched.add,
                        artifact_id=command.artifact_id, name=command.name, repo=live_repo, dry_run=False,
                    ))
                case ConnectElements():
                    source, target, kind = connection_id_as_written(command.artifact_id)
                    if command.op == "model.relation.edit":
                        require(edit_connection(
                            repo_root=staged, registry=registry, verifier=verifier, clear_repo_caches=touched.add,
                            source_entity=source, connection_type=kind, target_entity=target,
                            description=command.description, src_multiplicity=command.src_multiplicity,
                            tgt_multiplicity=command.tgt_multiplicity, dry_run=False,
                        ))
                        continue
                    require(add_connection(
                        repo_root=staged, registry=registry, verifier=verifier, clear_repo_caches=touched.add,
                        source_entity=source, connection_type=kind, target_entity=target,
                        description=command.description, src_multiplicity=command.src_multiplicity,
                        tgt_multiplicity=command.tgt_multiplicity, version="0.1.0", status="draft",
                        last_updated=None, dry_run=False,
                    ))
        repo, _, verifier = context()
        diagram = save_diagram(staged, repo, verifier, touched.add, False)
        require(diagram)
        # The replacement first removes the diagram's references. Other diagrams still protect the element.
        for command in commands:
            if isinstance(command, DeleteElement):
                _, registry, _ = context()
                require(delete_entity(repo_root=staged, registry=registry, clear_repo_caches=touched.add,
                                      artifact_id=command.artifact_id, dry_run=False))
        for suffix in (".svg", ".png"):
            output = rendered_path_for(diagram.path, staged, suffix)
            if output.is_file():
                touched.add(output)
        if not dry_run:
            commit_staged_repo(live_root=root, staged_root=staged, touched_paths=touched,
                               rebuild_index=lambda result: changed(result.changed_paths + result.deleted_paths))
        verification = dict(diagram.verification or {})
        if "path" in verification:
            verification["path"] = path_in_live(verification["path"], staged_root=staged, live_root=root)
        verification["issues"] = [
            {**issue, "location": location_in_live(issue.get("location"), staged, root)}
            for issue in verification.get("issues", [])
        ]
        return replace(diagram, path=root / diagram.path.relative_to(staged), wrote=not dry_run,
                       warnings=[text_in_live(w, staged, root) for w in diagram.warnings], verification=verification)
    finally:
        staging.cleanup()
