"""Deployment-configuration adapter for the signal-mutation capability
predicate: reads the configured storage backends and the live lock state, and
answers whether signal mutations are allowed right now — the single gate every
signal-mutation transport (REST, MCP) consults before touching a connector."""

from __future__ import annotations

from src.application.security_signals.capability import (
    SignalMutationCapability,
    signal_mutation_capability,
)
from src.config.storage_settings import (
    storage_assurance_archive_backend,
    storage_assurance_signals_backend,
    storage_assurance_store_backend,
)


def current_signal_mutation_capability(*, unlocked: bool) -> SignalMutationCapability:
    return signal_mutation_capability(
        store_backend=storage_assurance_store_backend(),
        signals_backend=storage_assurance_signals_backend(),
        archive_backend=storage_assurance_archive_backend(),
        unlocked=unlocked,
    )
