"""Tests for the ModelAndBind orchestration use case (WU-G5-P2)."""

from __future__ import annotations

from typing import Any

from src.application import assurance_model_bind as mb


class _FakeArchive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, operation: str, *, node_id: str | None = None,
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ops.append(operation)
        return {"operation": operation}


class _FakeStore:
    """In-memory store covering the surface model_and_bind + mutations + verifier touch."""

    def __init__(self, node: dict[str, Any] | None, *, unlocked: bool = True) -> None:
        self._unlocked = unlocked
        self._node = node
        self.arch_refs: list[tuple[str, str, str]] = []
        self.dropped = False  # simulate the node disappearing mid-flow

    def is_unlocked(self) -> bool:
        return self._unlocked

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if self.dropped or self._node is None or self._node["node_id"] != node_id:
            return None
        return self._node

    def register_arch_ref(self, nid: str, aid: str, ref_type: str) -> None:
        self.arch_refs.append((nid, aid, ref_type))

    def update_node(self, node_id: str, **attrs: Any) -> None:
        if self._node is not None:
            self._node.update(attrs)

    def list_nodes(self, **_kw: Any) -> list[dict[str, Any]]:
        return [] if (self._node is None or self.dropped) else [self._node]

    def list_edges(self, **_kw: Any) -> list[dict[str, Any]]:
        return []

    def list_arch_refs(self, **_kw: Any) -> list[dict[str, Any]]:
        return [{"assurance_node_id": n, "arch_artifact_id": a, "ref_type": r}
                for n, a, r in self.arch_refs]


class _FakeCreator:
    def __init__(self, *, known: bool = True, drop_store: _FakeStore | None = None) -> None:
        self.known = known
        self.created: list[tuple[str, str]] = []
        self._drop_store = drop_store

    def is_known_type(self, artifact_type: str) -> bool:
        return self.known

    def create(self, artifact_type: str, name: str) -> str:
        self.created.append((artifact_type, name))
        if self._drop_store is not None:
            self._drop_store.dropped = True  # node vanishes after entity creation
        return "APP@123.created"


def _node(binding: str = "unbound-pending") -> dict[str, Any]:
    return {
        "node_id": "CSN@1.x.y", "node_type": "control-structure-node",
        "name": "Brake Controller", "status": "draft", "tlp": "TLP:WHITE",
        "binding_status": binding,
    }


def _bind(store: _FakeStore, archive: _FakeArchive, creator: Any = None) -> mb.ModelBindResult:
    return mb.model_and_bind(
        store, archive,
        assurance_node_id="CSN@1.x.y",
        suggested_arch_type="application-component",
        suggested_name="Brake Controller",
        arch_creator=creator,
    )


# ── Preconditions ────────────────────────────────────────────────────────────────


def test_locked_store() -> None:
    assert isinstance(_bind(_FakeStore(_node(), unlocked=False), _FakeArchive()), mb.BindLocked)


def test_node_not_found() -> None:
    assert isinstance(_bind(_FakeStore(None), _FakeArchive()), mb.BindNotFound)


def test_wrong_binding_status_is_invalid() -> None:
    result = _bind(_FakeStore(_node(binding="bound")), _FakeArchive())
    assert isinstance(result, mb.BindInvalid)
    assert result.error == "invalid_binding_status"


# ── TaskRequired (no creator / separation of duties) ─────────────────────────────


def test_no_creator_returns_task_spec() -> None:
    archive = _FakeStore(_node()), _FakeArchive()
    result = _bind(*archive, creator=None)
    assert isinstance(result, mb.TaskRequired)
    assert result.spec["action_required"] == "create_arch_entity_then_bind"
    assert result.spec["step_1"]["on_server"] == "arch-repo-write"
    assert result.spec["step_2"]["params"]["ref_type"] == "binds-to"
    # No mutation happened.
    assert archive[1].ops == []


def test_unknown_arch_type_is_invalid() -> None:
    store = _FakeStore(_node())
    result = _bind(store, _FakeArchive(), creator=_FakeCreator(known=False))
    assert isinstance(result, mb.BindInvalid)
    assert result.error == "unknown_arch_type"


# ── Bound (creator present) ──────────────────────────────────────────────────────


def test_bound_creates_registers_and_marks_bound() -> None:
    store = _FakeStore(_node())
    archive = _FakeArchive()
    creator = _FakeCreator()
    result = _bind(store, archive, creator=creator)
    assert isinstance(result, mb.Bound)
    assert result.arch_artifact_id == "APP@123.created"
    assert creator.created == [("application-component", "Brake Controller")]
    assert store.arch_refs == [("CSN@1.x.y", "APP@123.created", "binds-to")]
    assert store._node is not None and store._node["binding_status"] == "bound"
    assert "MODEL_AND_BIND" in archive.ops


def test_binding_failure_after_create_returns_compensating_task() -> None:
    # Entity is created, then the node disappears → binding can't land.
    store = _FakeStore(_node())
    creator = _FakeCreator(drop_store=store)
    result = _bind(store, _FakeArchive(), creator=creator)
    assert isinstance(result, mb.TaskRequired)
    assert "was created but the assurance binding did not complete" in result.spec["note"]
    assert creator.created  # entity WAS created
    # Node was never marked bound (left unbound-pending).
    assert store.arch_refs == []
