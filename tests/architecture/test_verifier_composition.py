"""Infrastructure must build verifiers through the composition-root factory.

`ArtifactVerifier` lives in the application layer, which may not import infrastructure, so
its fallback PlantUML syntax port is a no-op that returns no issues. `check_puml_syntax`
nonetheless defaults to True. A verifier constructed directly therefore *reports* a clean
syntax result for every diagram without running PlantUML at all — and that is exactly what
every production path did until this test existed: GUI, MCP, bulk write and delete,
promotion and model exchange all constructed the verifier directly, so PlantUML syntax
verification never ran anywhere in the product.

Wiring it per construction site is what allowed that, and would allow the next site to
regress the same way, silently. So the rule is structural: inside `src/`, only the factory
constructs `ArtifactVerifier`.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"

# The factory itself, and the application layer that owns the class.
_ALLOWED = {
    "src/infrastructure/verification/verifier_factory.py",
    "src/application/verification/artifact_verifier.py",
}


def _construction_sites() -> list[str]:
    sites: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if rel in _ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "ArtifactVerifier":
                sites.append(f"{rel}:{node.lineno}")
    return sites


def test_only_the_factory_constructs_the_verifier() -> None:
    sites = _construction_sites()
    assert sites == [], (
        "ArtifactVerifier is constructed outside "
        "src/infrastructure/verification/verifier_factory.py:\n  "
        + "\n  ".join(sites)
        + "\n\nUse build_artifact_verifier(...) instead. Direct construction leaves the "
        "PlantUML syntax port unwired, so the verifier silently reports every diagram as "
        "syntactically clean while `check_puml_syntax` is True."
    )


def test_the_factory_wires_a_real_puml_port() -> None:
    """The point of the factory: the port must not be the application's null fallback."""
    from src.application.verification._verifier_stdlib_adapters import _NullPumlSyntax
    from src.infrastructure.verification.adapters import DefaultPumlSyntaxAdapter
    from src.infrastructure.verification.verifier_factory import build_artifact_verifier

    verifier = build_artifact_verifier(catalogs=_catalogs())
    port = verifier._puml_syntax
    assert isinstance(port, DefaultPumlSyntaxAdapter)
    assert not isinstance(port, _NullPumlSyntax)


def test_disabling_the_check_does_not_build_the_subprocess_adapter() -> None:
    """Paths that must not spawn a subprocess skip the check explicitly rather than
    appearing to run one — the distinction the null fallback used to blur."""
    from src.infrastructure.verification.verifier_factory import build_artifact_verifier

    verifier = build_artifact_verifier(catalogs=_catalogs(), check_puml_syntax=False)
    assert verifier.check_puml_syntax is False
    assert verifier._puml_port is None


def _catalogs():
    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry

    return build_runtime_catalogs(get_module_registry())
