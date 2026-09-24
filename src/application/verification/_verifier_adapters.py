"""Which adapter the artifact verifier talks to for each I/O concern, defaulted where one is not given.

Its own mixin because resolving the adapters is one concern and `ArtifactVerifier` is at the
source-length ceiling. A default is the stdlib adapter where one exists; where the real one needs a
library or a subprocess — PlantUML syntax, decoding an icon picture — a verifier built without it
skips that check explicitly, and `build_artifact_verifier` is what supplies the real ones.
"""

from __future__ import annotations

import functools

from src.application.verification.verifier_ports import (
    FileInventoryPort,
    IncrementalStatePort,
    PumlSyntaxPort,
    StoredPictureInspector,
    VerifierScheduler,
)


class _VerifierAdapters:
    _puml_port: PumlSyntaxPort | None
    _scheduler_port: VerifierScheduler | None
    _inventory_port: FileInventoryPort | None
    _incremental_port: IncrementalStatePort | None
    _picture_inspector: StoredPictureInspector | None

    @functools.cached_property
    def _puml_syntax(self) -> PumlSyntaxPort:
        if self._puml_port is not None:
            return self._puml_port
        from src.application.verification._verifier_stdlib_adapters import _NullPumlSyntax  # noqa: PLC0415

        return _NullPumlSyntax()

    @functools.cached_property
    def _scheduler(self) -> VerifierScheduler:
        if self._scheduler_port is not None:
            return self._scheduler_port
        from src.application.verification._verifier_stdlib_adapters import ThreadPoolVerifierScheduler  # noqa: PLC0415

        return ThreadPoolVerifierScheduler()

    @functools.cached_property
    def _inventory(self) -> FileInventoryPort:
        if self._inventory_port is not None:
            return self._inventory_port
        from src.application.verification._verifier_stdlib_adapters import FilesystemInventoryAdapter  # noqa: PLC0415

        return FilesystemInventoryAdapter()

    @functools.cached_property
    def _incremental(self) -> IncrementalStatePort:
        if self._incremental_port is not None:
            return self._incremental_port
        from src.application.verification._verifier_stdlib_adapters import (
            DefaultIncrementalStateAdapter,  # noqa: PLC0415
        )

        return DefaultIncrementalStateAdapter()
