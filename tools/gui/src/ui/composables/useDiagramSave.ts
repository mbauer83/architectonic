/**
 * Saving an edit session into its stored diagram: what the session changed, written as one replacement where
 * what the diagram holds changes (membership and layout together, D12) or as a layout patch where only the
 * arrangement does, and what the server said when it refused.
 *
 * Split from the edit session (`useDiagramEditing`), which decides what is drawn; this decides how it is
 * written. A replacement carries the revision the session read (`base_revision`), so a diagram changed since
 * is refused (409) rather than written over: the session is then stale and offers to read the diagram again.
 */
import { type Ref, ref, type ShallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { ArrangedLayout, StoredLayout } from '../../domain/layout/arrangementLayout'
import { layoutPatchBetween, patchIsEmpty } from '../../domain/layout/arrangementLayout'
import { composeCanvas } from '../../domain/layout/canvasComposition'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { membershipOf } from '../../domain/layout/diagramMembership'
import type { PendingChange } from '../../domain/layout/sessionChanges'
import type { LayoutPatch } from '../../ports/DiagramLayoutRepository'
import { failureOf, formatEffectError, isConflict } from '../lib/errors'
import type { ArrangementSession, ArrangementState } from './useArrangementSession'

/** What a save reads of its session, and what it moves on once written. */
export interface SaveTarget {
  readonly svc: Pick<ModelService, 'editDiagram' | 'getDiagram' | 'patchLayout'>
  readonly session: ArrangementSession
  /** The stored diagram a save writes into. */
  readonly diagramId: () => string
  /** Where the session started from: what a save is counted against, and moves on to. */
  readonly saved: ShallowRef<ArrangementState | null>
  readonly stored: ShallowRef<StoredLayout | null>
  readonly savedMembers: ShallowRef<DrawnMembership | null>
  readonly changes: Readonly<Ref<readonly PendingChange[]>>
  /** The layout the session would store, and the entity ids it removed. */
  readonly wanted: () => ArrangedLayout | null
  readonly removedIds: () => ReadonlySet<string>
  /** The revision of the diagram as the session last read it. */
  readonly revisionRead: () => string | undefined
  /** Read the diagram again after a replacement, and tell the page what it holds changed. */
  readonly reopen: () => Promise<void>
  readonly onMembershipSaved: () => void
  /** Where a refusal is said; shared with the session's own reads. */
  readonly error: Ref<string | null>
}

export function useDiagramSave(target: SaveTarget) {
  const { svc, session, saved, stored, savedMembers, error } = target
  const saving = ref(false)
  /** Whether the last save was refused because the diagram changed since it was read (409). */
  const stale = ref(false)

  /**
   * Write what the diagram holds less what was removed, through the diagram write, and read the picture
   * it draws now, keeping the arrangement of everything still on it.
   */
  const writeMembership = async (removed: ReadonlySet<string>, layoutPatch: LayoutPatch): Promise<void> => {
    const drawn = savedMembers.value
    if (!drawn) throw new Error('The diagram has not been read; reload the page.')
    const state = session.state.value
    if (!state) return
    const { write } = composeCanvas(drawn, state, removed)
    const revision = target.revisionRead()
    const written = await Effect.runPromise(svc.editDiagram(target.diagramId(), {
      ...write, ...(state.commands?.length ? { commands: state.commands } : {}),
      ...(revision ? { base_revision: revision } : {}),
      layout_patch: layoutPatch,
      dry_run: false,
    }))
    if (!written.wrote) {
      throw new Error(`The diagram was not written: ${written.warnings.join(' ') || 'it was refused'}`)
    }
    // Regrouped or with boxes edited, the groupings are the server's to identify: read back what it wrote.
    savedMembers.value = state.regroupings?.length || state.groupings
      ? membershipOf(await Effect.runPromise(svc.getDiagram(target.diagramId()))) : write
    await target.reopen()
    target.onMembershipSaved()
  }

  /** Write the arrangement alone, as a patch of the stored layout. */
  const writeLayout = async (patch: LayoutPatch): Promise<boolean> => {
    const result = await Effect.runPromise(svc.patchLayout(target.diagramId(), patch, false))
    if (result.errors.length > 0) {
      error.value = result.errors.join(' ')
      return false
    }
    stored.value = result.layout.elements || result.layout.boxes || result.layout.z ? result.layout : null
    saved.value = session.state.value
    return true
  }

  /** Write what the session changed. Stays in edit mode; what was saved is the new starting point. */
  const save = async (): Promise<boolean> => {
    const now = session.state.value
    if (!session.geometry.value || !now) return false
    const removed = target.removedIds()
    const patch = layoutPatchBetween(stored.value ?? {}, target.wanted())
    if (patchIsEmpty(patch) && target.changes.value.length === 0) return true
    saving.value = true
    error.value = null
    stale.value = false
    try {
      // One write when what the diagram holds changes: membership and layout together, so the stored
      // layout always matches the body that write generates (D12).
      if (removed.size > 0 || now.additions?.size || now.commands?.length || now.overlays?.length
        || now.regroupings?.length || now.occurrences?.length || now.drawnRelations?.length || now.groupings) {
        await writeMembership(removed, patch)
        return true
      }
      if (patchIsEmpty(patch)) {
        saved.value = session.state.value
        return true
      }
      return await writeLayout(patch)
    } catch (rejected) {
      // Read through the error envelope: a refusal says why (a body written by hand, a diagram changed since
      // read) instead of showing the response body.
      const failure = failureOf(rejected)
      error.value = formatEffectError(failure)
      stale.value = isConflict(failure)
      return false
    } finally {
      saving.value = false
    }
  }

  return { saving, stale, save }
}
