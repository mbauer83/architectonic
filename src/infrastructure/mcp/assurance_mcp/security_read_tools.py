"""Security-signal read-only MCP tools.

Tools registered on arch-assurance-read:
  assurance_list_bom_components  — components of the anchor's ACTIVE signal snapshot
  assurance_list_vulnerabilities — vulnerability findings of the active snapshot
  assurance_vulnerability_impact — REVERSE lookup: which entities one vulnerability affects
  assurance_security_stats       — signal-snapshot aggregate counts
  assurance_security_metrics     — posture metrics from the active signal snapshot + VEX
  assurance_scan_ai_candidates   — heuristic AI-BOM candidate scan
  assurance_aibom_export         — emit CycloneDX 1.6 ML-BOM from provided components JSON

All read the signal-snapshot model. Confidential-backend reads are gated behind store-unlock
and filtered by the max_classification TLP ceiling before return.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context


def register_security_read_tools(server: FastMCP) -> None:
    ctx = get_assurance_context()

    def _policy():  # type: ignore[no-untyped-def]
        from src.application.assurance_exposure import AssuranceExposurePolicy  # noqa: PLC0415

        return AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())

    @server.tool(
        name="assurance_list_bom_components",
        description=(
            "List the software components of the ACTIVE security signal snapshot for an "
            "architecture anchor (the current SBOM). Exposure-filtered by the TLP ceiling. "
            "Requires the assurance store to be unlocked."
        ),
    )
    def assurance_list_bom_components(anchor_entity_id: str) -> dict[str, object]:
        from src.application.security_signals.signals_read import list_active_components  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        snapshot_store = ctx.snapshot_store
        if snapshot_store is None:
            return {"components": [], "count": 0, "reason": "no co-located signals store"}
        components, withheld = list_active_components(
            anchor_entity_id, snapshot_store=snapshot_store, policy=_policy())
        return {"components": components, "count": len(components), "withheld": withheld}

    @server.tool(
        name="assurance_list_vulnerabilities",
        description=(
            "List vulnerability findings of the ACTIVE signal snapshot(s), each carrying its "
            "assessed_entity_id (the architecture entity the snapshot is attached to), component "
            "name/purl/directness, severity band, CVSS score, and applicability. "
            "assessed_entity_id (formerly required as anchor_entity_id) is OPTIONAL: omit it to "
            "list findings across ALL assessed entities (the cross-entity view — pair with "
            "assurance_security_stats.assessed_entities), or pass one to scope to a single entity. "
            "Optionally scope to one component by purl or component_id. Exposure-filtered; a "
            "finding is hidden when its component is. Requires the assurance store to be unlocked."
        ),
    )
    def assurance_list_vulnerabilities(
        assessed_entity_id: str | None = None, purl: str | None = None, component_id: str | None = None,
    ) -> dict[str, object]:
        from src.application.security_signals.signals_read import (  # noqa: PLC0415
            list_active_findings,
            list_all_active_findings,
        )

        if not ctx.is_available():
            return ctx.locked_response()
        snapshot_store = ctx.snapshot_store
        if snapshot_store is None:
            return {"findings": [], "count": 0, "reason": "no co-located signals store"}
        if assessed_entity_id is None:
            findings, withheld = list_all_active_findings(
                snapshot_store=snapshot_store, policy=_policy(), purl=purl, component_id=component_id)
        else:
            findings, withheld = list_active_findings(
                assessed_entity_id, snapshot_store=snapshot_store, policy=_policy(),
                purl=purl, component_id=component_id)
        return {"findings": findings, "count": len(findings), "withheld": withheld}

    @server.tool(
        name="assurance_vulnerability_impact",
        description=(
            "Find every architecture entity currently affected by ONE vulnerability — the "
            "reverse of the per-anchor listings. Accepts any identifier the vulnerability is "
            "known by (CVE, GHSA, PYSEC, or the canonical id): they resolve to one canonical "
            "identity, so the answer does not depend on which feed's id you hold, and the "
            "aliases are returned so you can see the others. "
            "Reads ACTIVE snapshots only — a superseded scan is history, not current exposure. "
            "Each affected entity lists the components through which it is affected, with "
            "severity, directness, and any current VEX status; a suppressed finding is "
            "REPORTED with its status rather than dropped, so a consciously-assessed "
            "entity is distinguishable from one that was never scanned (open_entity_count "
            "counts only the unsuppressed). Exposure-filtered before aggregation. "
            "An identifier this store has never seen is reported as not found, which is "
            "different from a known vulnerability that currently affects nothing. "
            "Requires the assurance store to be unlocked."
        ),
    )
    def assurance_vulnerability_impact(identifier: str) -> dict[str, object]:
        from src.infrastructure.assurance.signal_impact import (  # noqa: PLC0415
            find_vulnerability_impact,
        )

        if not ctx.is_available():
            return ctx.locked_response()
        snapshot_store = ctx.snapshot_store
        vex_store = ctx.vex_store
        if snapshot_store is None or vex_store is None:
            return {"found": False, "affected": [], "reason": "no co-located signals store"}
        return find_vulnerability_impact(
            identifier, impact_store=snapshot_store, vex_store=vex_store, policy=_policy())

    @server.tool(
        name="assurance_security_stats",
        description=(
            "Snapshot aggregate counts plus the assessed entities. Returns total_snapshots, "
            "active_snapshots, assessed_entity_count, active_snapshot_bom_components, "
            "active_snapshot_findings, and assessed_entities — a list of the architecture entities "
            "with an active signal snapshot, each with {entity_id, snapshot_id, bom_component_count, "
            "finding_count}. Use assessed_entities to discover which entities carry signals without "
            "an out-of-band lookup, then drill in with assurance_list_vulnerabilities / "
            "assurance_security_metrics. Requires the assurance store to be unlocked."
        ),
    )
    def assurance_security_stats() -> dict[str, object]:
        from src.application.security_signals.signals_read import signals_stats  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        snapshot_store = ctx.snapshot_store
        if snapshot_store is None:
            return {"reason": "no co-located signals store"}
        return dict(signals_stats(snapshot_store=snapshot_store))

    @server.tool(
        name="assurance_security_metrics",
        description=(
            "Security posture metrics for one architecture anchor, computed from the "
            "single ACTIVE signal snapshot plus visible VEX assessments, exposure-filtered "
            "before any aggregation. Unit-explicit: finding_total and per-directness "
            "open_component_findings count component findings; "
            "distinct_open_vulnerabilities counts canonical vulnerability identities. "
            "Includes basis snapshot id/timestamp, computed classification, and closed "
            "availability/content states (no_active_snapshot / no_findings / "
            "visibility_limited / complete)."
        ),
    )
    def assurance_security_metrics(anchor_entity_id: str) -> dict[str, object]:
        from dataclasses import asdict  # noqa: PLC0415

        from src.application.assurance_exposure import AssuranceExposurePolicy  # noqa: PLC0415
        from src.application.security_signals.metrics import compute_security_metrics  # noqa: PLC0415

        if not ctx.is_available():
            return ctx.locked_response()
        snapshot_store = ctx.snapshot_store
        vex_store = ctx.vex_store
        if snapshot_store is None or vex_store is None:
            return {
                "availability": "unavailable",
                "reason": "metrics require the SQLCipher store with co-located signals",
            }
        policy = AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())
        return asdict(compute_security_metrics(
            anchor_entity_id, snapshot_store=snapshot_store, vex_store=vex_store, policy=policy,
        ))

    @server.tool(
        name="assurance_scan_ai_candidates",
        description=(
            "Heuristic AI-BOM candidate scan over a list of architecture entity dicts. "
            "Ranks entities by name patterns (gpt/claude/llm/embedding/mcp-server/agent/rag/vector), "
            "type, and connection structure. Returns a ranked list for the user/agent to confirm. "
            "Results are assistive, never authoritative — confirm before marking. "
            "Pass the output of arch-repo-read list/query tools as 'entities'."
        ),
    )
    def assurance_scan_ai_candidates(
        entities: list[dict[str, object]],
    ) -> dict[str, object]:
        from src.infrastructure.assurance.ai_candidate_scanner import scan_candidates  # noqa: PLC0415

        candidates = scan_candidates(entities)
        return {
            "candidates": candidates,
            "count": len(candidates),
            "note": (
                "These are heuristic suggestions only. Confirm each candidate, then MARK it "
                "by setting an AI specialization on the entity via arch-repo-write's "
                "artifact_edit_entity (specialization=ai-model | ai-agent | "
                "ai-inference-service | ai-dataset | ai-prompt-asset | ai-vector-store | "
                "ai-runtime | ai-tool-interface). Marking is an architecture write, not an "
                "assurance one; there is no assurance_mark_ai_component tool."
            ),
        }

    @server.tool(
        name="assurance_aibom_export",
        description=(
            "Emit a CycloneDX 1.6 ML-BOM/ASBOM JSON document from a list of AI-component dicts. "
            "Each component dict should have: name (required), purl, cpe, ai_role "
            "(machine-learning-model | dataset | inference-service | mcp-server | tool | "
            "agent | orchestrator | prompt | guardrail | vector-store | rag-pipeline), "
            "version, provider, hosted, external, arch_entity_id. "
            "The emitted BOM can be sealed into the archive via assurance_seal_baseline."
        ),
    )
    def assurance_aibom_export(
        ai_components: list[dict[str, object]],
        notes: str = "",
    ) -> dict[str, object]:
        from src.infrastructure.assurance._aibom_exporter import build_cyclonedx_16  # noqa: PLC0415

        bom = build_cyclonedx_16(ai_components, notes=notes)
        return {"bom": bom, "component_count": len(ai_components)}
