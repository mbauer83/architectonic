from __future__ import annotations

import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.domain.deployment.layout import ENV_SETTINGS_PATH
from src.domain.viewpoints.viewpoints import EnforcementSetting

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def settings_document_path() -> Path:
    """The active settings document.

    Honors the `ARCH_SETTINGS_PATH` process selector (stage 1 of the deployment
    layout — Docker exports it so runtime and upgrade read the same document);
    falls back to the source-tree compatibility default.
    """
    env = os.environ.get(ENV_SETTINGS_PATH)
    return Path(env).expanduser() if env else _CONFIG_DIR / "settings.yaml"


_DEFAULT_ENGAGEMENT: dict[str, object] = {}
_DEFAULTS: dict[str, dict[str, object]] = {
    "backend": {
        "port": 8000,
        "log_path": ".arch/backend.log",
        "min_log_level": "INFO",
        "slow_request_warning_s": 5.0,
        "request_thread_dump_s": 20.0,
    },
    "diagrams": {
        "archimate_type_markers": "labels",
        "sprite_scale": 1.5,
        "render_dpi": 150,
        "plantuml_limit_size": 16384,
    },
    "repo_init": {
        "default_branch": "main",
        "commit_author_name": "arch-switch-engagement",
        "commit_author_email": "arch-switch-engagement@local.invalid",
        "engagement": _DEFAULT_ENGAGEMENT,
    },
    "storage": {
        "assurance": {
            "store_backend": "sqlcipher",
            "signals_backend": "sqlcipher-colocated",
            "archive_backend": "standard",
            "max_classification": "TLP:AMBER",
            "activation_policy": "manual",
        },
        "read_model": {},
    },
    "validation": {
        "datatype_type_references_blocking": True,
        "viewpoint_enforcement": "warn",
    },
    "guidance": {
        # The published guidance document. An operator points this elsewhere to serve their own;
        # nothing is fetched until `arch-import-guidance` is run, so the default is a location, not
        # a call-home.
        "default_source": (
            "https://raw.githubusercontent.com/mbauer83/architecture-modeling-guidance/"
            "refs/heads/main/guidance.yaml"
        ),
    },
    "viewpoints": {
        "execution_max_entities": 500,
        "execution_default_entity_limit_mcp": 200,
        "execution_timeout_seconds": 10,
        "max_query_bindings": 8,
        "max_query_parameters": 4,
        "max_derived_attributes": 8,
        "derivation_max_hops": 4,
        "derivation_max_relationships": 20000,
        "derivation_time_budget_seconds": 2.0,
        "diagram_render_max_entities": 250,
        "legibility_budget": 100,
    },
    "exchange": {
        "max_document_bytes": 10_000_000,
    },
    "assurance": {
        "neighbors_default_max_hops": 1,
        "neighbors_max_hops": 4,
        "neighbors_max_nodes": 150,
        "neighbors_max_edges": 300,
        "neighbors_time_budget_seconds": 2.0,
    },
}




_SettingsSection = dict[str, object]


def load_settings() -> dict:
    path = settings_document_path()
    if not path.exists():
        return _DEFAULTS.copy()
    data: dict[str, object] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    backend_raw = data.get("backend")
    diagrams_raw = data.get("diagrams")
    repo_init_raw = data.get("repo_init")
    backend_section: _SettingsSection = backend_raw if isinstance(backend_raw, dict) else {}
    diagrams_section: _SettingsSection = diagrams_raw if isinstance(diagrams_raw, dict) else {}
    repo_init_section: _SettingsSection = repo_init_raw if isinstance(repo_init_raw, dict) else {}
    repo_init_engagement_raw = repo_init_section.get("engagement")
    repo_init_engagement_section: _SettingsSection = (
        repo_init_engagement_raw if isinstance(repo_init_engagement_raw, dict) else {}
    )
    backend = {**_DEFAULTS["backend"], **backend_section}
    diagrams = {**_DEFAULTS["diagrams"], **diagrams_section}
    repo_init = {
        **_DEFAULTS["repo_init"],
        **repo_init_section,
        "engagement": {
            **_DEFAULT_ENGAGEMENT,
            **repo_init_engagement_section,
        },
    }
    modules_raw = data.get("modules")
    modules_section: _SettingsSection = modules_raw if isinstance(modules_raw, dict) else {}

    storage_raw = data.get("storage")
    storage_section: _SettingsSection = storage_raw if isinstance(storage_raw, dict) else {}
    storage_assurance_raw = storage_section.get("assurance")
    storage_assurance: _SettingsSection = (
        storage_assurance_raw if isinstance(storage_assurance_raw, dict) else {}
    )
    storage_read_model_raw = storage_section.get("read_model")
    storage_read_model: _SettingsSection = (
        storage_read_model_raw if isinstance(storage_read_model_raw, dict) else {}
    )
    default_storage: dict[str, object] = _DEFAULTS["storage"]  # type: ignore[assignment]
    default_assurance: dict[str, object] = default_storage["assurance"]  # type: ignore[assignment]
    storage: dict[str, object] = {
        "assurance": {**default_assurance, **storage_assurance},
        "read_model": {**storage_read_model},
    }
    validation_raw = data.get("validation")
    validation_section: _SettingsSection = validation_raw if isinstance(validation_raw, dict) else {}
    validation = {**_DEFAULTS["validation"], **validation_section}

    guidance_raw = data.get("guidance")
    guidance_section: _SettingsSection = guidance_raw if isinstance(guidance_raw, dict) else {}
    guidance = {**_DEFAULTS["guidance"], **guidance_section}

    viewpoints_raw = data.get("viewpoints")
    viewpoints_section: _SettingsSection = viewpoints_raw if isinstance(viewpoints_raw, dict) else {}
    viewpoints = {**_DEFAULTS["viewpoints"], **viewpoints_section}

    exchange_raw = data.get("exchange")
    exchange_section: _SettingsSection = exchange_raw if isinstance(exchange_raw, dict) else {}
    exchange = {**_DEFAULTS["exchange"], **exchange_section}

    assurance_raw = data.get("assurance")
    assurance_section: _SettingsSection = assurance_raw if isinstance(assurance_raw, dict) else {}
    assurance = {**_DEFAULTS["assurance"], **assurance_section}

    return {
        "backend": backend,
        "diagrams": diagrams,
        "repo_init": repo_init,
        "modules": modules_section,
        "storage": storage,
        "validation": validation,
        "guidance": guidance,
        "viewpoints": viewpoints,
        "exchange": exchange,
        "assurance": assurance,
    }


def module_overrides() -> dict[str, dict[str, object]]:
    """Return the ``modules:`` section from settings.yaml as {name: override-dict}.

    Only ``enabled`` is a supported YAML override key. Absent modules default to
    the module's own manifest values (enabled=True, requires=[]).
    """
    raw = load_settings().get("modules", {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        parsed: dict[str, object] = {}
        if "enabled" in entry:
            parsed["enabled"] = bool(entry["enabled"])
        out[str(name)] = parsed
    return out


def backend_port() -> int:
    value = load_settings()["backend"].get("port", 8000)
    try:
        return max(1, min(65535, int(value)))
    except (TypeError, ValueError):
        return 8000


def _positive_seconds(key: str, fallback: float) -> float:
    value = load_settings()["backend"].get(key, fallback)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return fallback
    return seconds if seconds > 0 else fallback


def slow_request_warning_seconds() -> float:
    """How long a request may run before the backend logs a slow-request warning."""
    return _positive_seconds("slow_request_warning_s", 5.0)


def request_thread_dump_seconds() -> float:
    """How long a request may run before the backend dumps every thread's stack.

    Deliberately well above the slow-request threshold: a thread dump is the diagnostic
    for a request that is stuck rather than merely slow, and it is expensive to produce.
    """
    return _positive_seconds("request_thread_dump_s", 20.0)


def backend_log_path() -> str:
    value = load_settings()["backend"].get("log_path", ".arch/backend.log")
    if not isinstance(value, str) or not value.strip():
        return ".arch/backend.log"
    return value.strip()


def backend_min_log_level() -> str:
    value = load_settings()["backend"].get("min_log_level", "INFO")
    if not isinstance(value, str):
        return "INFO"
    normalized = value.strip().upper()
    if normalized == "WARN":
        return "WARNING"
    if normalized in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return normalized
    return "INFO"


def archimate_type_markers() -> str:
    value = load_settings()["diagrams"].get("archimate_type_markers", "labels")
    return value if value in {"labels", "icons"} else "labels"


def sprite_scale() -> float:
    value = load_settings()["diagrams"].get("sprite_scale", 1.5)
    try:
        return max(0.5, float(value))
    except (TypeError, ValueError):
        return 1.5


def render_dpi() -> int:
    value = load_settings()["diagrams"].get("render_dpi", 150)
    try:
        return max(72, int(value))
    except (TypeError, ValueError):
        return 150


def plantuml_limit_size() -> int:
    value = load_settings()["diagrams"].get("plantuml_limit_size", 16384)
    try:
        return max(4096, int(value))
    except (TypeError, ValueError):
        return 16384


def datatype_type_references_blocking() -> bool:
    """Whether E332/E334/E335/E336 reject writes instead of remaining advisory."""
    value = load_settings()["validation"].get("datatype_type_references_blocking", True)
    return value if isinstance(value, bool) else True


def viewpoint_enforcement_setting() -> EnforcementSetting:
    """Default viewpoint-application enforcement (W180/W181), overridable per-application."""
    value = str(load_settings()["validation"].get("viewpoint_enforcement", "warn"))
    if value not in ("off", "warn", "ghost"):
        return "warn"
    return value


def exchange_max_document_bytes() -> int:
    """Hard size cap on an incoming C19C model-exchange document — rejected before any parsing
    is attempted, independent of the parser's own entity-expansion defenses."""
    value = load_settings()["exchange"]["max_document_bytes"]
    try:
        return max(1, int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 10_000_000


def guidance_default_source() -> str:
    """Preconfigured ``--source`` default for ``arch-import-guidance``. Operational
    default only — never a governance/customization surface."""
    guidance = load_settings().get("guidance", {})
    if not isinstance(guidance, dict):
        return ""
    value = guidance.get("default_source", "")
    return value if isinstance(value, str) else ""


def _repo_init_value(key: str, repo_kind: str | None = None) -> object:
    repo_init = load_settings().get("repo_init", {})
    if not isinstance(repo_init, dict):
        repo_init = {}
    if repo_kind:
        scoped = repo_init.get(repo_kind)
        if isinstance(scoped, dict) and key in scoped:
            return scoped.get(key)
    return repo_init.get(key)


def repo_init_default_branch(repo_kind: str | None = None) -> str:
    value = _repo_init_value("default_branch", repo_kind)
    if not isinstance(value, str) or not value.strip():
        return "main"
    return value.strip()


def repo_init_commit_author_name(repo_kind: str | None = None) -> str:
    value = _repo_init_value("commit_author_name", repo_kind)
    if not isinstance(value, str) or not value.strip():
        return "arch-switch-engagement"
    return value.strip()


def repo_init_commit_author_email(repo_kind: str | None = None) -> str:
    value = _repo_init_value("commit_author_email", repo_kind)
    if not isinstance(value, str) or not value.strip():
        return "arch-switch-engagement@local.invalid"
    return value.strip()


