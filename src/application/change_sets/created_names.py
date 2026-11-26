"""What a stack of change sets creates, named as its sets name it and as everyone else names it.

Inside a set, an entity the set creates is named by its create's alias, a provisional reference
(`provisional_reference`): it has no id until something applies the set, and `coherence` refuses a set
that names its own create by the id chosen for it. A set read on top of another names what the lower one
creates the same way. That is the sets' business. A caller never has to know an alias:

* **what a caller states is read in the sets' terms** (`reference_for`): the id chosen for an entity
  the stack creates, in either spelling, names that create; anything else is taken as it is;
* **what a caller is answered is said in the caller's terms** (`spoken`, `named_by_id`,
  `named_in_sentence`): a provisional reference to a create that chose an id is that id, in its stable
  form, as every model id in an answer is.

Both directions read the one mapping, `chosen_ids`, so what is accepted and what is answered cannot
disagree. A create that chose no id keeps its reference both ways: there is nothing else to call it by.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.domain.artifact_id import canonical_entity_key
from src.domain.provisional_reference import alias_of, named_in_text, provisional

#: The id chosen for each entity a stack creates, by the alias its create states.
ChosenIds = Mapping[str, str]


def chosen_ids(sets: Iterable[ChangeSet]) -> dict[str, str]:
    """The id each create of *sets* chose, by its alias; a create that chose none is not named here."""
    return {create.ref: create.artifact_id for held in sets for create in held.created.values() if create.artifact_id}


def reference_for(spelled: str, chosen: ChosenIds) -> str:
    """The reference the sets name *spelled* with: a create's, where *spelled* is the id it chose (in either
    spelling); else *spelled* as it is — a model id, or a provisional reference already."""
    by_id = {canonical_entity_key(artifact_id): provisional(alias) for alias, artifact_id in chosen.items()}
    return by_id.get(canonical_entity_key(spelled), spelled)


def spoken(reference: str, chosen: ChosenIds) -> str:
    """*reference* as a caller is answered: the stable form of the id chosen for what it names, else as it is."""
    alias = alias_of(reference)
    artifact_id = chosen.get(alias) if alias is not None else None
    return canonical_entity_key(artifact_id) if artifact_id else reference


def named_by_id(operation: Operation, chosen: ChosenIds) -> Operation:
    """*operation* with each entity it names by the alias of a create in *chosen* named by that create's id."""
    return _renamed(operation, lambda reference: spoken(reference, chosen))


def named_by_alias(operation: Operation, chosen: ChosenIds) -> Operation:
    """*operation* with each entity it names by an id a create in *chosen* chose named by that create's alias."""
    return _renamed(operation, lambda reference: reference_for(reference, chosen))


def named_in_sentence(sentence: str, chosen: ChosenIds) -> str:
    """*sentence* — a standing's reason, a refusal — with each alias of a create in *chosen* written as its id."""
    return named_in_text(sentence, {alias: canonical_entity_key(artifact_id) for alias, artifact_id in chosen.items()})


def _renamed(operation: Operation, name: Callable[[str], str]) -> Operation:
    match operation:
        case CreateEntity():
            return operation
        case EditEntity(target=target) | RemoveEntity(target=target):
            return replace(operation, target=name(target))
        case AddConnection(address=address) | EditConnection(address=address) | RemoveConnection(address=address):
            return replace(operation, address=ConnectionAddress(
                name(address.source_entity), address.connection_type, name(address.target_entity),
            ))
