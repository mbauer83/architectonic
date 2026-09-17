"""The update phases on a local checkout: the one `UpdateActions` for the `local-checkout` kind.

Everything that must run as the *checkout's* version — the data upgrade, its restore, the asset
pins — is a subprocess through `uv run --project <checkout>`, so the same object works before the
handover (old code, old checkout), after it (new code, new checkout) and during a rollback (new code,
old checkout again). Everything else calls the owners the product already has: `backend_control`
stops, `backend_launch` starts, `activation` authorizes.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from src.application.software_update.installation import (
    BackendObservation,
    CheckoutMove,
    DependencySelection,
    GuiProvisioning,
)
from src.application.software_update.journal import TargetRelease
from src.application.software_update.ports import MigrationResult
from src.application.software_update.release import sha256_of
from src.infrastructure.software_update import gui_bundle, uv_environment
from src.infrastructure.software_update._commands import checkout_tool, run_checked, run_command
from src.infrastructure.software_update._migration import migration_result
from src.infrastructure.software_update.checkout import GitCheckout

_MIGRATION_TIMEOUT_SECONDS = 3600
_ASSET_TIMEOUT_SECONDS = 1800


class UpdateActionError(RuntimeError):
    pass


class LocalCheckoutActions:
    def __init__(
        self,
        root: Path,
        *,
        assets_dir: Path,
        deployment_arguments: Sequence[str],
        resolve_selection: Sequence[str] = (),
        uv: str = "uv",
    ) -> None:
        self.root = root
        self.assets_dir = assets_dir
        self.deployment_arguments = tuple(deployment_arguments)
        self.resolve_selection = tuple(resolve_selection)
        self.uv = uv

    # ── Backend ───────────────────────────────────────────────────────────────

    def stop_backend(self, port: int | None) -> None:
        from src.infrastructure.backend.backend_control import stop_backend  # noqa: PLC0415

        result = stop_backend(cwd=self.root, port=port)
        if not result.get("stopped") and result.get("reason") not in {"stale_pid", "not_running"}:
            raise UpdateActionError(f"the backend on port {port} could not be stopped: {result}")

    def start_backend(self, previous: BackendObservation) -> None:
        from src.infrastructure.backend.backend_launch import start_detached  # noqa: PLC0415

        if previous.port is None:
            raise UpdateActionError("the previous backend's port is not recorded")
        start_detached(previous.port, workspace=self.root, project_dir=self.root, flags=previous.flags)

    # ── Software ──────────────────────────────────────────────────────────────

    def move_checkout(self, tag: str, move: CheckoutMove) -> None:
        GitCheckout(self.root).move_to(tag, move)

    def restore_checkout(self, commit: str, branch: str | None) -> None:
        GitCheckout(self.root).restore(commit, branch)

    def sync_environment(self, selection: DependencySelection) -> None:
        uv_environment.sync(self.root, selection, uv=self.uv)

    def install_gui(self, gui: GuiProvisioning, target: TargetRelease) -> None:
        if gui in ("leave_stale", "in_image"):
            return
        if gui == "build_locally":
            gui_bundle.keep_previous(self.root)
            gui_bundle.build_locally(self.root)
            return
        if target.gui_bundle is None or target.gui_bundle_sha256 is None:
            raise UpdateActionError("the release's GUI bundle was not recorded for installation")
        try:
            data = (self.assets_dir / target.gui_bundle).read_bytes()
        except OSError as exc:
            raise UpdateActionError(f"the verified GUI bundle is not where the check left it: {exc}") from exc
        if sha256_of(data) != target.gui_bundle_sha256:
            raise UpdateActionError("the GUI bundle on disk no longer matches the digest it was verified against")
        gui_bundle.install_bundle(self.root, data)

    def restore_gui(self) -> None:
        gui_bundle.restore_previous(self.root)

    def reconcile_assets(self) -> tuple[str, ...]:
        """Re-pin plantuml.jar and the embedding model where the checkout's pins moved, as its version."""
        from src.infrastructure.bootstrap.embedding_model_asset import model_directory  # noqa: PLC0415

        changed: list[str] = []
        jar = run_command(
            self._tool("get-plantuml", "--check"), cwd=self.root, timeout=_ASSET_TIMEOUT_SECONDS,
            doing="checking plantuml.jar against its pin",
        )
        if jar.returncode != 0:
            run_checked(
                self._tool("get-plantuml", "--force"), cwd=self.root, timeout=_ASSET_TIMEOUT_SECONDS,
                doing="installing the pinned plantuml.jar",
            )
            changed.append("plantuml.jar re-provisioned to the pinned release")
        if model_directory().exists():
            model = run_command(
                self._tool("get-embedding-model", "--check"), cwd=self.root, timeout=_ASSET_TIMEOUT_SECONDS,
                doing="checking the embedding model against its pin",
            )
            if model.returncode != 0:
                run_checked(
                    self._tool("get-embedding-model"), cwd=self.root, timeout=_ASSET_TIMEOUT_SECONDS,
                    doing="installing the pinned embedding model",
                )
                changed.append("embedding model re-provisioned to the pinned revision")
        return tuple(changed)

    # ── Data ──────────────────────────────────────────────────────────────────

    def migrate(self) -> MigrationResult:
        extra = [arg for slug in self.resolve_selection for arg in ("--resolve-selection", slug)]
        doing = "arch-repair upgrade --commit"
        result = run_command(
            self._tool("arch-repair", "upgrade", "--commit", "--json", *self.deployment_arguments, *extra),
            cwd=self.root, timeout=_MIGRATION_TIMEOUT_SECONDS, doing=doing,
        )
        return migration_result(result, doing=doing)

    def restore_checkpoint(self, checkpoint_set: str) -> None:
        run_checked(
            self._tool("arch-repair", "upgrade", "--restore", checkpoint_set, *self.deployment_arguments),
            cwd=self.root, timeout=_MIGRATION_TIMEOUT_SECONDS, doing=f"arch-repair upgrade --restore {checkpoint_set}",
        )

    def authorize_store(self) -> None:
        from src.infrastructure.assurance.activation import activate_store  # noqa: PLC0415
        from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

        try:
            activate_store(resolve_manifest().assurance_db_path.path)
        except RuntimeError as exc:
            raise UpdateActionError(f"the assurance store could not be re-authorized: {exc}") from exc

    # ── Verification ──────────────────────────────────────────────────────────

    def verify(self, target: TargetRelease, *, backend_expected: bool) -> None:
        from src.infrastructure.backend.backend_control import backend_status  # noqa: PLC0415
        from src.infrastructure.backend.backend_probe import probe_identity_on_port  # noqa: PLC0415

        observed = GitCheckout(self.root).observe()
        if str(observed.version) != target.version:
            raise UpdateActionError(f"the checkout declares {observed.version}, not {target.version}")
        if not backend_expected:
            return
        status = backend_status(cwd=self.root)
        port = status.get("port")
        identity = probe_identity_on_port(port) if status.get("running") and isinstance(port, int) else None
        if identity is None:
            raise UpdateActionError("no backend answers for this workspace after the restart")
        if identity.software_version != target.version:
            raise UpdateActionError(f"the backend serves {identity.software_version}, not {target.version}")

    def _tool(self, tool: str, *arguments: str) -> list[str]:
        return checkout_tool(self.uv, self.root, tool, *arguments)
