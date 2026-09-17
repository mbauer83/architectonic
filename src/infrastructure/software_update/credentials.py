"""Answer the planner's credential questions before anything stops, and verify each answer.

Answers go into this process's environment: the re-executed new version inherits them, and so does
the detached backend it starts, through the variables `backend_launch` already reads. Nothing is
written to disk and nothing is echoed.
"""

from __future__ import annotations

import getpass
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from src.application.software_update.plan import CredentialQuestion

_ATTEMPTS = 3


class CredentialsUnavailable(RuntimeError):
    """A question could not be answered — no terminal, or the answer was rejected."""


def answer_questions(questions: Sequence[CredentialQuestion], root: Path, *, interactive: bool) -> tuple[str, ...]:
    """Ask each question and verify the answer; returns the environment names that were set."""
    answered: list[str] = []
    for question in questions:
        if question.kind == "git":
            _answer_git(root, interactive)
        else:
            _answer_vault_password(question, interactive)
        answered.append(question.env_name)
    return tuple(answered)


def _answer_git(root: Path, interactive: bool) -> None:
    from src.infrastructure.backend.backend_launch import workspace_git_credentials  # noqa: PLC0415
    from src.infrastructure.git.git_auth import (  # noqa: PLC0415
        GitCredentialError,
        credentials_to_env_overrides,
        has_env_credentials,
    )

    if not interactive and not has_env_credentials():
        raise CredentialsUnavailable(
            "the restarted backend needs git credentials and there is no terminal to ask at; set "
            "ARCH_GIT_SSH_PASSWORD or ARCH_GIT_HTTPS_TOKEN / ARCH_GIT_HTTPS_TOKEN_FILE"
        )
    try:
        credentials = workspace_git_credentials(root)
    except GitCredentialError as exc:
        raise CredentialsUnavailable(str(exc)) from exc
    os.environ.update(credentials_to_env_overrides(credentials))


def _answer_vault_password(question: CredentialQuestion, interactive: bool) -> None:
    if os.environ.get(question.env_name) and _vault_opens():
        return
    if not interactive:
        raise CredentialsUnavailable(
            f"{question.what} is needed ({question.why}) and there is no terminal to ask at; set {question.env_name}"
        )
    for attempt in range(_ATTEMPTS):
        password = getpass.getpass(f"{question.what} ({question.why}): ")
        os.environ[question.env_name] = password
        if _vault_opens():
            return
        print("That password does not open the vault.", file=sys.stderr)
        if attempt == _ATTEMPTS - 1:
            os.environ.pop(question.env_name, None)
    raise CredentialsUnavailable(f"{question.what} was not accepted after {_ATTEMPTS} attempts")


def _vault_opens() -> bool:
    from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    try:
        return bool(accounts.present(accounts.DB_KEY, resolve_manifest().assurance_db_path.path))
    except RuntimeError:
        return False
