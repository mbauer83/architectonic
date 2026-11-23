"""Importing a generic rule early must not change repository verification."""

import subprocess
import sys


def test_repository_rule_dispatch_is_independent_of_import_order() -> None:
    probe = """
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

rules = (
    ("_duplicate_identity_rules", "DuplicateStableIdContribution"),
    ("_exclusive_containment_rule", "ExclusiveContainmentContribution"),
    ("_orphan_attachment_schema_rule", "OrphanAttachmentSchemaContribution"),
    ("_undeclared_group_rule", "UndeclaredGroupContribution"),
    ("_workspace_identity_rules", "WorkspaceIdUniquenessContribution"),
)
for module, name in (rules if sys.argv[1] == "forward" else reversed(rules)):
    rule = getattr(importlib.import_module("src.application.verification." + module), name)
    rule.run = lambda self, ctx, result: print(type(self).__name__)
from src.application.verification._verifier_contribution_runner import run_repository_contributions
catalogs = SimpleNamespace(diagram_types=SimpleNamespace(all_diagram_types=lambda: {}))
run_repository_contributions(candidate=object(), runtime_catalogs=catalogs, repo_path=Path("."))
"""
    def dispatched(order: str) -> list[str]:
        return subprocess.check_output([sys.executable, "-c", probe, order], text=True).splitlines()

    forward = dispatched("forward")
    assert len(set(forward)) == 5
    assert dispatched("reverse") == forward
