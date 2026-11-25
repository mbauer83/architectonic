"""The installation's git checkout, observed and moved through the git package's one command runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from src.application.software_update.installation import CheckoutMove, CheckoutRelation, InstalledSoftware
from src.application.software_update.plan import SignatureVerdict
from src.application.software_update.version import NotAReleaseVersion, ReleaseVersion, parse_release_version
from src.infrastructure.deployment.layout import DEPLOYMENT_LOCAL_FILES
from src.infrastructure.git._git_command import GIT_TIMEOUT, PUSH_TIMEOUT, run_repo_git
from src.infrastructure.git.git_repository_state import current_branch, current_commit
from src.infrastructure.mutation_adapters import run_git

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
        modified = self._modified_tracked()
        configuration = _configuration_paths()
        return InstalledSoftware(
            version=self._declared_version(),
            commit=commit,
            branch=current_branch(self.root),
            modified_tracked=tuple(path for path in modified if path not in configuration),
            signers_file_present=(self.root / RELEASE_SIGNERS).is_file(),
            gui_stamp=self._gui_stamp(),
            plantuml_version=_pinned_plantuml_version(),
            local_configuration=tuple(path for path in modified if path in configuration),
            hidden_configuration=self._hidden(configuration),
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

    def relation_to(self, commit: str, configuration: tuple[str, ...]) -> CheckoutRelation:
        ancestor, _, _ = run_repo_git(self.root, "merge-base", "--is-ancestor", "HEAD", commit)
        rc, count, _ = run_repo_git(self.root, "rev-list", "--count", f"{commit}..HEAD")
        local_commits = int(count) if rc == 0 and count.strip().isdigit() else 0
        rc, base, _ = run_repo_git(self.root, "merge-base", "HEAD", commit)
        changed = tuple(path for path in configuration if self._changes(commit, path))
        conflicts = tuple(path for path in changed if self._carried(commit, path) is None)
        return CheckoutRelation(
            fast_forwardable=ancestor == 0,
            local_commits=local_commits,
            merge_base=base.strip() if rc == 0 and base.strip() else None,
            configuration_changed=changed,
            configuration_conflicts=conflicts,
        )

    # ── Moves ─────────────────────────────────────────────────────────────────

    def move_to(self, tag: str, move: CheckoutMove, *, carry: Path | None = None) -> None:
        """Bring the working tree to `tag`: fast-forward the current branch, or detach onto the tag.

        Configuration edits the tag does not touch stay in the working tree, as git keeps any local
        change a move leaves alone. One the tag also changes would make git refuse the move, so with a
        `carry` directory it is saved there, reset, and merged onto the tag's version afterwards (the
        dry run has already refused a conflicting one). `restore` puts the saved edits back.
        """
        target = f"{tag}^{{commit}}"
        carried: dict[str, str] = {}
        if carry is not None:
            for path in self.observe().local_configuration:
                if self._changes(target, path):
                    carried[path] = (self.root / path).read_text(encoding="utf-8")
            _save_carried(carry, carried)
            for path in carried:
                self._git("checkout", "--", path, doing=f"setting {path} aside")
        rc, previous, _ = run_repo_git(self.root, "rev-parse", "HEAD")
        if move == "fast_forward":
            rc, _, stderr = run_repo_git(self.root, "merge", "--ff-only", target)
        else:
            rc, _, stderr = run_repo_git(self.root, "checkout", "--detach", target)
        if rc != 0:
            raise CheckoutError(f"moving the checkout to {tag}: {stderr}")
        for path, ours in carried.items():
            merged = _merge_three_way(ours, self._show(previous.strip(), path), self._show("HEAD", path))
            if merged is None:
                raise CheckoutError(f"the local edits to {path} conflict with {tag}'s change to it")
            (self.root / path).write_text(merged, encoding="utf-8")

    def restore(self, commit: str, branch: str | None, *, carry: Path | None = None) -> None:
        """Return to `commit`, on `branch` where there was one — `reset --keep`, so a local change made
        since is refused rather than discarded. Configuration edits `move_to` carried are put back as
        they were before the move."""
        carried = _load_carried(carry)
        for path in carried:
            self._git("checkout", "--", path, doing=f"undoing the merge into {path}")
        self._restore_commit(commit, branch)
        for path, content in carried.items():
            (self.root / path).write_text(content, encoding="utf-8")
        if carry is not None:
            shutil.rmtree(carry, ignore_errors=True)

    def _restore_commit(self, commit: str, branch: str | None) -> None:
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

    def _hidden(self, configuration: frozenset[str]) -> tuple[str, ...]:
        """Configuration files flagged skip-worktree (`S`) or assume-unchanged (lower-case tag)."""
        rc, out, _ = run_repo_git(self.root, "ls-files", "-v", "--", *sorted(configuration))
        if rc != 0:
            return ()
        hidden = []
        for line in out.splitlines():
            tag, _, path = line.partition(" ")
            if tag == "S" or (tag.islower() and tag):
                hidden.append(path)
        return tuple(hidden)

    def _changes(self, commit: str, path: str) -> bool:
        rc, _, _ = run_repo_git(self.root, "diff", "--quiet", "HEAD", commit, "--", path)
        return rc == 1

    def _carried(self, commit: str, path: str) -> str | None:
        """The local edits to *path* merged onto *commit*'s version, or None where they conflict."""
        ours = (self.root / path).read_text(encoding="utf-8")
        return _merge_three_way(ours, self._show("HEAD", path), self._show(commit, path))

    def _show(self, revision: str, path: str) -> str:
        result = _untrimmed_git(self.root, "show", f"{revision}:{path}")
        if result.returncode != 0:
            raise CheckoutError(f"reading {path} at {revision[:12]}: {result.stderr.strip()}")
        return result.stdout

    def _git(self, *args: str, doing: str) -> None:
        rc, _, stderr = run_repo_git(self.root, *args)
        if rc != 0:
            raise CheckoutError(f"{doing}: {stderr}")

    def _gui_stamp(self) -> str | None:
        try:
            stamp = json.loads((self.root / GUI_BUILD_STAMP).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return str(stamp.get("hash")) if isinstance(stamp, dict) and stamp.get("hash") else None


def _pinned_plantuml_version() -> str | None:
    from src.infrastructure.bootstrap.get_plantuml import PLANTUML_VERSION  # noqa: PLC0415

    return PLANTUML_VERSION


_CARRIED_INDEX = "carried.json"


def _configuration_paths() -> frozenset[str]:
    return frozenset(path.as_posix() for path in DEPLOYMENT_LOCAL_FILES)


def _merge_three_way(ours: str, base: str, theirs: str) -> str | None:
    """`git merge-file` over three texts: the merged text, or None when the two sides conflict."""
    with tempfile.TemporaryDirectory(prefix="arch-update-carry-") as scratch:
        files = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(scratch) / name
            path.write_text(text, encoding="utf-8")
            files.append(str(path))
        result = _untrimmed_git(Path(scratch), "merge-file", "-p", *files)
    return result.stdout if result.returncode == 0 else None


def _untrimmed_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """`git *args` with its output as written: file contents keep their final newline."""
    return run_git(cwd, args, timeout=GIT_TIMEOUT, env=dict(os.environ))


def _save_carried(carry: Path, carried: dict[str, str]) -> None:
    carry.mkdir(parents=True, exist_ok=True)
    (carry / _CARRIED_INDEX).write_text(json.dumps(carried), encoding="utf-8")


def _load_carried(carry: Path | None) -> dict[str, str]:
    if carry is None or not (carry / _CARRIED_INDEX).is_file():
        return {}
    loaded = json.loads((carry / _CARRIED_INDEX).read_text(encoding="utf-8"))
    return {str(path): str(text) for path, text in loaded.items()} if isinstance(loaded, dict) else {}
