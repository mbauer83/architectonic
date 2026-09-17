"""The installation's git checkout, observed and moved through the git package's one command runner."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from src.application.software_update.installation import CheckoutMove, InstalledSoftware
from src.application.software_update.plan import SignatureVerdict
from src.application.software_update.version import NotAReleaseVersion, ReleaseVersion, parse_release_version
from src.infrastructure.git._git_command import PUSH_TIMEOUT, run_repo_git
from src.infrastructure.git.git_repository_state import current_branch, current_commit

RELEASE_SIGNERS = Path(".github") / "release-signers"
GUI_BUILD_STAMP = Path("tools") / "gui" / "dist" / "build-stamp.json"


class CheckoutError(RuntimeError):
    pass


class GitCheckout:
    def __init__(self, root: Path) -> None:
        self.root = root

    # ── Checkout port ─────────────────────────────────────────────────────────

    def observe(self) -> InstalledSoftware:
        commit = current_commit(self.root)
        if commit is None:
            raise CheckoutError(f"{self.root} is not a git checkout with a HEAD commit")
        return InstalledSoftware(
            version=self._declared_version(),
            commit=commit,
            branch=current_branch(self.root),
            modified_tracked=self._modified_tracked(),
            signers_file_present=(self.root / RELEASE_SIGNERS).is_file(),
            gui_stamp=self._gui_stamp(),
            plantuml_version=_pinned_plantuml_version(),
        )

    def fetch_tag(self, tag: str) -> str | None:
        rc, _, stderr = run_repo_git(self.root, "fetch", "--no-tags", "origin", "tag", tag, timeout=PUSH_TIMEOUT)
        if rc != 0:
            if "couldn't find remote ref" in stderr or "not found" in stderr:
                return None
            raise CheckoutError(f"fetching {tag}: {stderr}")
        rc, commit, stderr = run_repo_git(self.root, "rev-parse", f"{tag}^{{commit}}")
        if rc != 0:
            raise CheckoutError(f"resolving {tag}: {stderr}")
        return commit

    def verify_tag(self, tag: str) -> SignatureVerdict:
        """Judge the tag's signature against the signers file *this* checkout carries.

        Enforcement follows the installed version: a checkout without the file cannot say who may
        sign, so the verdict is `not_enforced` and the planner turns it into a note rather than a
        refusal. Once the file exists, `git verify-tag` decides, and its two failure shapes are told
        apart so the report can say "unsigned" or "signed by a key this installation does not trust".
        """
        signers = self.root / RELEASE_SIGNERS
        if not signers.is_file():
            return "not_enforced"
        rc, _, stderr = run_repo_git(
            self.root,
            "-c", "gpg.format=ssh",
            "-c", f"gpg.ssh.allowedSignersFile={signers}",
            "verify-tag", tag,
        )
        if rc == 0:
            return "verified"
        if "no signature found" in stderr.lower():
            return "unsigned"
        return "untrusted"

    def on_main_branch(self) -> bool:
        return current_branch(self.root) == "main"

    # ── Moves ─────────────────────────────────────────────────────────────────

    def move_to(self, tag: str, move: CheckoutMove) -> None:
        """Bring the working tree to `tag`: fast-forward the current branch, or detach onto the tag."""
        if move == "fast_forward":
            rc, _, stderr = run_repo_git(self.root, "merge", "--ff-only", f"{tag}^{{commit}}")
        else:
            rc, _, stderr = run_repo_git(self.root, "checkout", "--detach", f"{tag}^{{commit}}")
        if rc != 0:
            raise CheckoutError(f"moving the checkout to {tag}: {stderr}")

    def restore(self, commit: str, branch: str | None) -> None:
        """Return to `commit`, on `branch` where there was one — `reset --keep`, so a local change made
        since is refused rather than discarded."""
        if branch is not None:
            rc, _, stderr = run_repo_git(self.root, "checkout", branch)
            if rc != 0:
                raise CheckoutError(f"returning to branch {branch}: {stderr}")
            rc, _, stderr = run_repo_git(self.root, "reset", "--keep", commit)
        else:
            rc, _, stderr = run_repo_git(self.root, "checkout", "--detach", commit)
        if rc != 0:
            raise CheckoutError(f"returning the checkout to {commit[:7]}: {stderr}")

    # ── Observations ──────────────────────────────────────────────────────────

    def _declared_version(self) -> ReleaseVersion | None:
        try:
            project = tomllib.loads((self.root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            return parse_release_version(str(project["version"]))
        except (OSError, KeyError, tomllib.TOMLDecodeError, NotAReleaseVersion):
            return None

    def _modified_tracked(self) -> tuple[str, ...]:
        """Tracked files with local modifications, staged or not, `.arch/` excluded.

        Names only, from `diff`, rather than porcelain status lines: the command runner trims its
        output, and a porcelain line's first column is a space for an unstaged change, so the first
        letter of the first file name went with it.
        """
        modified: list[str] = []
        for staged in ((), ("--cached",)):
            rc, out, stderr = run_repo_git(
                self.root, "diff", "--name-only", *staged, "HEAD", "--", ".", ":(exclude).arch",
            )
            if rc != 0:
                raise CheckoutError(f"git diff: {stderr}")
            modified.extend(line for line in out.splitlines() if line.strip())
        return tuple(sorted(set(modified)))

    def _gui_stamp(self) -> str | None:
        try:
            stamp = json.loads((self.root / GUI_BUILD_STAMP).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return str(stamp.get("hash")) if isinstance(stamp, dict) and stamp.get("hash") else None


def _pinned_plantuml_version() -> str | None:
    from src.infrastructure.bootstrap.get_plantuml import PLANTUML_VERSION  # noqa: PLC0415

    return PLANTUML_VERSION
