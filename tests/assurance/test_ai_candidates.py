"""Tests for AI-component candidate heuristic scanner."""

from __future__ import annotations

from src.infrastructure.assurance.ai_candidate_scanner import scan_candidates


def _ent(name: str, entity_type: str = "application-component", ai_role: str = "") -> dict:
    e: dict = {"name": name, "entity_type": entity_type, "entity_id": f"ACP@{name}"}
    if ai_role:
        e["ai_role"] = ai_role
    return e


class TestScanCandidates:
    def test_empty_entities(self) -> None:
        assert scan_candidates([]) == []

    def test_llm_name_pattern(self) -> None:
        results = scan_candidates([_ent("gpt-4o-inference-service")])
        assert len(results) == 1
        assert results[0]["score"] > 0
        assert any("LLM" in r or "AI provider" in r for r in results[0]["reasons"])

    def test_mcp_server_pattern(self) -> None:
        results = scan_candidates([_ent("github-mcp-server")])
        assert len(results) == 1
        assert results[0]["score"] >= 30

    def test_embedding_pattern(self) -> None:
        results = scan_candidates([_ent("text-embedding-service")])
        assert len(results) == 1
        assert results[0]["score"] > 0

    def test_non_ai_entity_zero_score_excluded(self) -> None:
        results = scan_candidates([_ent("payment-gateway"), _ent("order-database")])
        assert results == []

    def test_sorted_by_score_desc(self) -> None:
        entities = [
            _ent("plain-service"),          # no score
            _ent("gpt-llm-orchestrator"),   # high score (LLM + orchestrator + provider)
            _ent("vector-store-api"),       # medium score
        ]
        results = scan_candidates(entities)
        assert len(results) >= 2
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_already_marked_excluded(self) -> None:
        results = scan_candidates([_ent("claude-service", ai_role="inference-service")])
        assert results == []

    def test_entity_with_ai_specialization_is_skipped(self) -> None:
        # WU-E2: marking now sets an AI specialization (not the legacy ai_role). An entity
        # already carrying one must be skipped — this branch was unreachable before.
        marked = {"name": "claude-service", "entity_type": "application-component",
                  "specializations": ["ai-model"]}
        assert scan_candidates([marked]) == []

    def test_entity_with_scalar_ai_specialization_is_skipped(self) -> None:
        marked = {"name": "gpt-service", "entity_type": "application-component",
                  "specialization": "ai-inference-service"}
        assert scan_candidates([marked]) == []

    def test_non_ai_specialization_does_not_skip(self) -> None:
        # A plain (non-AI) specialization must NOT suppress a name-matched candidate.
        cand = {"name": "llm-gateway", "entity_type": "application-component",
                "specializations": ["module"]}
        assert scan_candidates([cand]) != []

    def test_technology_service_bonus(self) -> None:
        svc = _ent("llm-gateway", entity_type="technology-service")
        app = _ent("llm-gateway", entity_type="application-component")
        r_svc = scan_candidates([svc])
        r_app = scan_candidates([app])
        assert r_svc[0]["score"] > r_app[0]["score"]

    def test_rag_keyword(self) -> None:
        results = scan_candidates([_ent("rag-retrieval-pipeline")])
        assert results[0]["score"] >= 25

    def test_vector_store_keyword(self) -> None:
        results = scan_candidates([_ent("pinecone-vector-db")])
        assert results[0]["score"] >= 25

    def test_score_capped_at_100(self) -> None:
        # Name with many matching patterns should not exceed 100
        results = scan_candidates([_ent("openai-gpt-llm-agent-mcp-server-embedding")])
        assert results[0]["score"] <= 100

    def test_reasons_present(self) -> None:
        results = scan_candidates([_ent("gpt-service")])
        assert len(results[0]["reasons"]) > 0
