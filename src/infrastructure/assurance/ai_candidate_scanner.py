"""Heuristic AI-component candidate scanner.

scan_candidates() accepts a list of architecture entity dicts and returns a
ranked list of candidates that are likely AI-BOM-relevant, based on name
patterns, type patterns, and connection structure.

Each result has: entity_id, name, entity_type, score, reasons.
The score is 0..100 (higher = more confident). The caller must confirm;
results are never authoritative.
"""

from __future__ import annotations

import re

_NAME_PATTERNS: list[tuple[re.Pattern[str], int, str]] = [
    (re.compile(r"\b(gpt|claude|gemini|mistral|llama|falcon|phi|qwen)\b", re.I), 35, "LLM name pattern"),
    (re.compile(r"\b(llm|large.language.model)\b", re.I), 30, "LLM keyword"),
    (re.compile(r"\b(embedding[s]?|vectori[sz]er)\b", re.I), 25, "embedding keyword"),
    (re.compile(r"\b(rag|retrieval.augmented)\b", re.I), 25, "RAG keyword"),
    (re.compile(r"\bmcp.server\b", re.I), 30, "MCP server name"),
    (re.compile(r"\b(agent|orchestrat)\b", re.I), 20, "agent/orchestrator keyword"),
    (re.compile(r"\b(vector.?store|vector.?db|pinecone|weaviate|qdrant|chroma)\b", re.I), 25, "vector store"),
    (re.compile(r"\b(dataset[s]?|training.?data|fine.?tun)\b", re.I), 20, "dataset keyword"),
    (re.compile(r"\b(inference|predict|ml.?model|model.?card)\b", re.I), 20, "inference/model keyword"),
    (re.compile(r"\b(guardrail[s]?|prompt.?guard|content.?filter)\b", re.I), 20, "guardrail keyword"),
    (re.compile(r"\b(tool.?call|function.?call|tool.?use)\b", re.I), 15, "tool-call pattern"),
    (re.compile(r"\b(openai|anthropic|cohere|hugging.?face|replicate)\b", re.I), 30, "AI provider name"),
]

_TYPE_BONUSES: dict[str, int] = {
    "application-component": 5,
    "technology-service": 10,
    "application-interface": 8,
    "data-object": 5,
    "artifact": 3,
    "system-software": 5,
}


def _already_ai_marked(ent: dict[str, object]) -> bool:
    """True when the entity already carries an AI specialization — a scalar ``specialization``
    or any of a ``specializations`` list. Such an entity is already an AIBOM component, so the
    heuristic scan skips it rather than re-suggesting it."""
    from src.application.aibom_derivation import AI_SPECIALIZATIONS  # noqa: PLC0415

    scalar = ent.get("specialization")
    if isinstance(scalar, str) and scalar in AI_SPECIALIZATIONS:
        return True
    listed = ent.get("specializations")
    if isinstance(listed, (list, tuple)):
        return any(isinstance(s, str) and s in AI_SPECIALIZATIONS for s in listed)
    return False


def scan_candidates(entities: list[dict[str, object]]) -> list[dict[str, object]]:
    """Score architecture entity dicts for AI-BOM relevance.

    Input entity dicts must have at least 'name' and optionally 'entity_id',
    'entity_type', 'domain', and 'description'.

    Returns candidates with score > 0, sorted descending by score.
    """
    results: list[dict[str, object]] = []
    for ent in entities:
        name = str(ent.get("name") or "")
        desc = str(ent.get("description") or ent.get("content") or "")
        entity_type = str(ent.get("entity_type") or ent.get("type") or "")
        entity_id = str(ent.get("entity_id") or ent.get("id") or "")

        score = 0
        reasons: list[str] = []

        # Already marked — skip. Marking = an AI specialization on the entity (the current
        # model; `ai_role` is the legacy dict field kept for back-compat).
        if ent.get("ai_role") or _already_ai_marked(ent):
            continue

        combined_text = f"{name} {desc}"
        for pattern, weight, label in _NAME_PATTERNS:
            if pattern.search(combined_text):
                score += weight
                reasons.append(label)

        # Type bonus only amplifies an existing name-based signal
        if score > 0:
            type_bonus = _TYPE_BONUSES.get(entity_type, 0)
            if type_bonus:
                score += type_bonus
                reasons.append(f"entity type: {entity_type}")

        if score > 0:
            results.append({
                "entity_id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "score": min(score, 100),
                "reasons": reasons,
            })

    results.sort(key=lambda x: -(x["score"] or 0))  # type: ignore[operator]
    return results
