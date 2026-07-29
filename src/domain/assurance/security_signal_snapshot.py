"""Security signal-snapshot lifecycle: state machine, idempotent-replay decisions,
and the canonical bundle digest.

A signal snapshot is the atomic unit of security-signal ingestion: one anchor, one
staged population of components/aliases/vulnerabilities/findings, one atomic
activation. Metrics only ever read the single active snapshot per anchor.

Lifecycle: ``staging → complete → active → superseded`` plus the terminal
``staging → failed``. Status never doubles as a timestamp — activation and
supersession carry their own fields. ``failed`` is TERMINAL: replaying the same
request returns the stored failure and instructs the caller to use a new
``request_id``; it never resumes.

Idempotency: ``(anchor_entity_id, request_id)`` is the replay key (one bundle
has exactly one anchor); ``request_payload_digest`` is the SHA-256 of the
canonical accepted bundle — every semantic field after normalization,
deliberately NOT the BOM digest (the BOM is not the whole command).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from src.domain.artifact_id import canonical_entity_key

SnapshotStatus = Literal["staging", "complete", "active", "superseded", "failed"]

_ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("staging", "complete"),
    ("staging", "failed"),
    ("complete", "active"),
    ("active", "superseded"),
})

TERMINAL_STATUSES: frozenset[str] = frozenset({"failed", "superseded"})


def is_allowed_transition(current: str, target: str) -> bool:
    return (current, target) in _ALLOWED_TRANSITIONS


def transition_error(current: str, target: str) -> str:
    return (
        f"Illegal signal-snapshot transition {current!r} → {target!r}; allowed: "
        + ", ".join(sorted(f"{a}→{b}" for a, b in _ALLOWED_TRANSITIONS))
    )


# ── Which architecture elements may anchor a snapshot ─────────────────────────

#: Admissible anchors, as (artifact type → permitted specializations). ``None``
#: means every specialization of that type qualifies; a frozenset restricts to the
#: listed ones, where ``""`` is the unspecialized form.
#:
#: An SBOM is a bill of materials for ONE built, independently shipped artifact,
#: which is what constrains this. An application-component that is a *service* (or
#: an unspecialized one, which is the same thing before anyone has bothered to
#: specialize it) is such an artifact; a *module* is a part of one, so its
#: dependencies belong to whatever ships it, and an *endpoint* is an interface,
#: which is not built at all. Technology nodes and system software are shipped
#: artifacts in their own right — a container image or a database engine has a bill
#: of materials — so every specialization of those qualifies.
#:
#: ``None`` rather than ``frozenset({""})`` for the technology types on purpose:
#: neither declares specializations today, and enumerating the empty case would
#: silently refuse every anchor the moment the ontology gained one.
#:
#: Owned HERE rather than in a client so the GUI, REST and MCP surfaces cannot
#: disagree about what may be anchored, and ENFORCED by the ingest command so the
#: rule is not merely advisory to whoever happens to read it.
ADMISSIBLE_ANCHORS: Mapping[str, frozenset[str] | None] = {
    "application-component": frozenset({"", "service"}),
    "node": None,
    "system-software": None,
}

#: The bare types, for surfaces that only need the coarse vocabulary (entity
#: pickers, "can this element anchor signals?" affordances).
ADMISSIBLE_ANCHOR_TYPES: tuple[str, ...] = tuple(ADMISSIBLE_ANCHORS)


@dataclass(frozen=True)
class AnchorDescriptor:
    """What the architecture model says about a prospective anchor."""

    entity_id: str
    artifact_type: str
    specialization: str = ""


@dataclass(frozen=True)
class AnchorAdmissible:
    """The anchor exists and may carry security signals."""

    entity_id: str


@dataclass(frozen=True)
class AnchorUnknown:
    """No such architecture entity. A snapshot anchored on nothing is unreachable
    from the model, so this is refused rather than stored."""

    entity_id: str


@dataclass(frozen=True)
class AnchorTypeNotPermitted:
    """The entity exists but is not a thing an SBOM can describe."""

    entity_id: str
    artifact_type: str
    specialization: str

    def message(self) -> str:
        described = (
            f"{self.artifact_type}/{self.specialization}"
            if self.specialization else self.artifact_type
        )
        permitted = ", ".join(
            artifact_type if specs is None else
            f"{artifact_type} ({', '.join(spec or 'unspecialized' for spec in sorted(specs))})"
            for artifact_type, specs in sorted(ADMISSIBLE_ANCHORS.items())
        )
        return (
            f"{self.entity_id} is a {described}, which cannot anchor security "
            f"signals. An SBOM describes one built, independently shipped artifact; "
            f"permitted anchors are: {permitted}."
        )


AnchorDecision = AnchorAdmissible | AnchorUnknown | AnchorTypeNotPermitted


def evaluate_anchor(entity_id: str, descriptor: AnchorDescriptor | None) -> AnchorDecision:
    """Decide whether an ingest may be anchored on this entity.

    A missing descriptor means the architecture model does not know the id — the
    ingest already REQUIRES an anchor, so accepting one that resolves to nothing
    would store a snapshot no model surface can ever reach.
    """
    if descriptor is None:
        return AnchorUnknown(entity_id=entity_id)
    if descriptor.artifact_type not in ADMISSIBLE_ANCHORS:
        return AnchorTypeNotPermitted(
            entity_id=entity_id,
            artifact_type=descriptor.artifact_type,
            specialization=descriptor.specialization,
        )
    permitted = ADMISSIBLE_ANCHORS[descriptor.artifact_type]
    if permitted is not None and descriptor.specialization not in permitted:
        return AnchorTypeNotPermitted(
            entity_id=entity_id,
            artifact_type=descriptor.artifact_type,
            specialization=descriptor.specialization,
        )
    return AnchorAdmissible(entity_id=entity_id)


# ── Anchor identity ────────────────────────────────────────────────────────────


def anchor_key(anchor_entity_id: str) -> str:
    """The key a snapshot is stored and looked up under: the stable (slug-free) artifact id.

    Named separately from the general canonicaliser because a snapshot anchor has a second reason
    to be slug-free that other keys do not: the slug is rename-volatile, so keying on the full id
    would orphan every snapshot the moment its anchor entity is renamed.
    """
    return canonical_entity_key(anchor_entity_id)


# ── Idempotent replay ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoredSnapshotKey:
    """What the store knows about an existing snapshot under the replay key."""

    snapshot_id: str
    status: str
    request_payload_digest: str


@dataclass(frozen=True)
class CreateNewSnapshot:
    """No snapshot exists under the key — begin a new staging snapshot."""


@dataclass(frozen=True)
class ReplayInProgress:
    """Same key + digest, snapshot not yet terminal/active: retry later; no mutation."""

    snapshot_id: str


@dataclass(frozen=True)
class ReplayStoredSuccess:
    """Same key + digest, snapshot reached active (or was later superseded):
    return the original success; no mutation, no new audit."""

    snapshot_id: str


@dataclass(frozen=True)
class ReplayStoredFailure:
    """Same key + digest, snapshot failed (terminal): return the stored failure and
    instruct the caller to use a new request_id; no mutation, no new audit."""

    snapshot_id: str


@dataclass(frozen=True)
class IdempotencyConflict:
    """Same key, DIFFERENT digest: typed conflict; no signal or audit write."""

    snapshot_id: str
    stored_digest: str
    submitted_digest: str


ReplayDecision = (
    CreateNewSnapshot | ReplayInProgress | ReplayStoredSuccess | ReplayStoredFailure | IdempotencyConflict
)


def replay_decision(existing: StoredSnapshotKey | None, submitted_digest: str) -> ReplayDecision:
    """The normative replay table for one (anchor, request_id) key."""
    if existing is None:
        return CreateNewSnapshot()
    if existing.request_payload_digest != submitted_digest:
        return IdempotencyConflict(
            snapshot_id=existing.snapshot_id,
            stored_digest=existing.request_payload_digest,
            submitted_digest=submitted_digest,
        )
    if existing.status in ("staging", "complete"):
        return ReplayInProgress(snapshot_id=existing.snapshot_id)
    if existing.status in ("active", "superseded"):
        return ReplayStoredSuccess(snapshot_id=existing.snapshot_id)
    return ReplayStoredFailure(snapshot_id=existing.snapshot_id)


# ── What a population actually persisted ──────────────────────────────────────


@dataclass(frozen=True)
class SnapshotPopulation:
    """The outcome of populating one snapshot: what was submitted, and what the
    store actually holds afterwards.

    The two differ by design. Row identity is ``(snapshot, component, canonical
    vulnerability)``, so two submitted findings whose alias sets resolve to the
    same canonical vulnerability for the same component collapse into one row —
    one component plus one canonical vulnerability is exactly one finding. That
    collapse is correct; reporting only the submitted count is not, because the
    caller then reads back a smaller number than the ingest claimed. Both counts
    travel together so the collapse stays visible instead of being swallowed.
    """

    canonical_by_external_id: Mapping[str, str]
    submitted_component_count: int
    persisted_component_count: int
    submitted_finding_count: int
    persisted_finding_count: int

    @property
    def collapsed_finding_count(self) -> int:
        """Submitted findings that merged into an existing row via alias resolution."""
        return self.submitted_finding_count - self.persisted_finding_count

    @property
    def collapsed_component_count(self) -> int:
        """Submitted components that merged into an existing row by source id."""
        return self.submitted_component_count - self.persisted_component_count


# ── Canonical bundle digest ────────────────────────────────────────────────────


def _canonical(value: object) -> object:
    """Normalization for digesting: mappings key-sorted recursively; sequences
    of mappings sorted by their canonical JSON so input ordering never changes
    the digest; scalars unchanged."""
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        canon = [_canonical(item) for item in value]
        return sorted(canon, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True))
    return value


def canonical_bundle_digest(semantic_fields: Mapping[str, object]) -> str:
    """SHA-256 over the canonical form of every semantic bundle field
    (components, findings, aliases, applicability evaluations, diagnostics,
    generator/source metadata, anchor) — generated fields (snapshot id, timestamps)
    must not be passed in."""
    canonical = _canonical(semantic_fields)
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# ── Directness classification (I-C9) ──────────────────────────────────────────


def classify_directness(
    root_ref: str,
    component_ref: str,
    dependency_edges: Sequence[tuple[str, str]],
) -> Literal["direct", "transitive", "unknown"]:
    """BFS depth from the BOM root over the dependency graph: the root itself is
    not a dependency; depth 1 = direct; reachable depth ≥ 2 = transitive;
    unreachable (or cycle-locked away from the root) = unknown. Cycles terminate
    via the visited set."""
    if component_ref == root_ref:
        return "unknown"
    children: dict[str, list[str]] = {}
    for parent, child in dependency_edges:
        children.setdefault(parent, []).append(child)
    visited: set[str] = {root_ref}
    frontier = [root_ref]
    depth = 0
    while frontier:
        depth += 1
        next_frontier: list[str] = []
        for node in frontier:
            for child in children.get(node, []):
                if child == component_ref:
                    return "direct" if depth == 1 else "transitive"
                if child not in visited:
                    visited.add(child)
                    next_frontier.append(child)
        frontier = next_frontier
    return "unknown"
