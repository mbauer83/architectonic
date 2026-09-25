"""The written paraphrases describe their elements without naming them, and still name live elements.

A paraphrase that repeats a word of its element's name is a name query in disguise, and would let
keyword search answer the question the stratum exists to ask of retrieval by meaning. Names change,
so this is checked against the repository as it stands: renaming an element to a word its paraphrase
uses fails here, which is the moment the paraphrase needs rewording.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.workspace_paths import resolve_workspace_repo_roots
from src.domain.artifact_id import stable_id
from src.infrastructure.artifact_index import shared_artifact_index
from tools.quality.paraphrase_queries import PARAPHRASES

#: Words a name and a description may share without the description naming anything.
_FUNCTION_WORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "by", "with", "as", "is", "at", "from", "its",
    "it", "be",
})


def _words(text: str) -> set[str]:
    return {word.strip(".,:;()&'\"").lower() for word in text.replace("-", " ").split()} - _FUNCTION_WORDS - {""}


@pytest.fixture(scope="module")
def names_by_key() -> dict[str, str]:
    roots = resolve_workspace_repo_roots(Path(__file__).resolve().parents[2])
    if not roots:
        pytest.skip("no workspace configuration")
    store = shared_artifact_index(roots[0])
    store.refresh()
    entities = (store.get_entity(artifact_id) for artifact_id in store.entity_ids())
    return {stable_id(entity.artifact_id): entity.name for entity in entities if entity is not None}


def test_no_paraphrase_repeats_a_word_of_its_elements_name(names_by_key: dict[str, str]) -> None:
    repeated = {
        key: sorted(_words(query) & _words(names_by_key[key]))
        for key, query in PARAPHRASES
        if key in names_by_key and _words(query) & _words(names_by_key[key])
    }
    assert repeated == {}, f"these paraphrases name what they ask for: {repeated}"


def test_every_paraphrase_is_keyed_once(names_by_key: dict[str, str]) -> None:
    keys = [key for key, _ in PARAPHRASES]
    assert len(keys) == len(set(keys)), "a paraphrase key appears twice; each element is asked for once"
