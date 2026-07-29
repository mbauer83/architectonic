"""Strong type wrappers and sentinels for the ontology module system."""

from __future__ import annotations

from typing import ClassVar, Final, NewType, final

EntityTypeName = NewType("EntityTypeName", str)
ConnectionTypeName = NewType("ConnectionTypeName", str)
DiagramTypeName = NewType("DiagramTypeName", str)
ElementClassName = NewType("ElementClassName", str)


@final
class _FreeOntologyType:
    """Singleton sentinel. Diagram types bound here accept entities from any registered ontology."""

    _instance: ClassVar[_FreeOntologyType | None] = None

    def __new__(cls) -> _FreeOntologyType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "FreeOntology"


FreeOntology: Final[_FreeOntologyType] = _FreeOntologyType()
