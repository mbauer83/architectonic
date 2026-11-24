/**
 * A diagram's edit session on its own page: the arranging session (`useArrangementSession`) over the
 * picture the diagram is arranged on, read against what the diagram last stored.
 *
 * Nothing persists until Save, and what Save would write is read off the state, never counted: the
 * arrangement now against the one last saved (`arrangedUnits`). So returning to automatic leaves no
 * arranging change, a move undone leaves none, and the count follows Undo and Redo (owner, F3).
 *
 * Taking a picture over writes it down as a first layout is: PlantUML's arrangement with its narrow
 * gaps widened (`widenedArrangement`), the same rule the server's first layout applies.
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { ArrangedLayout, StoredLayout } from '../../domain/layout/arrangementLayout'
import {
  arrangedBy, arrangedUnits, layoutOf, layoutPatchBetween, patchIsEmpty, shownRoutesOfMoved,
} from '../../domain/layout/arrangementLayout'
import type { Arrangement } from '../../domain/layout/lab/labArrangement'
import { drawnArrangement } from '../../domain/layout/lab/labArrangement'
import { widenedArrangement } from '../../domain/layout/lab/labRouting'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { composeCanvas } from '../../domain/layout/canvasComposition'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import type { LayoutPatch } from '../../ports/DiagramLayoutRepository'
import { stableEntityId } from '../../domain/artifactId'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ArrangementState } from './useArrangementSession'
import { useArrangementSession } from './useArrangementSession'

/** One row of what Save would write, in the product's words. */
export interface PendingChange {
  readonly key: string
  readonly text: string
  readonly model?: boolean
}

export function useDiagramEditing(
  svc: ModelService, diagramId: () => string, membership: () => DrawnMembership | null,
  onMembershipSaved: () => void = () => {},
) {
  const session = useArrangementSession(
    (shapes) => svc.drawResizedShapes(diagramId(), shapes),
    (geometry, automatic) => widenedArrangement(geometry, automatic),
  )
  /** The layout the diagram stored when the session opened or last saved; null while PlantUML arranges it. */
  const stored = shallowRef<StoredLayout | null>(null)
  /** Where the session started from, and where Discard returns to. */
  const saved = shallowRef<ArrangementState | null>(null)
  const savedMembers = shallowRef<DrawnMembership | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const savedState = (geometry: LayoutGeometry, layout: StoredLayout | null): ArrangementState =>
    layout ? { arrangement: arrangedBy(geometry, layout), byHand: true }
      : { arrangement: drawnArrangement(geometry), byHand: false }

  /** Read the picture as stored and start from it; *carried* is an arrangement to keep, as a save does. */
  const reopen = async (carried: ArrangedLayout | null = null): Promise<void> => {
    const geometry = await Effect.runPromise(svc.readLayoutGeometry(diagramId()))
    const layout = geometry.layout && (geometry.layout.elements || geometry.layout.boxes) ? geometry.layout : null
    stored.value = layout
    saved.value = { ...savedState(geometry, layout), picture: geometry }
    session.open(geometry, carried ? { arrangement: arrangedBy(geometry, carried), byHand: true } : saved.value)
  }

  /**
   * Open on the picture as stored; *commands* are content already proposed elsewhere, drawn at once and
   * not undoable: they are where the session starts, as the stored picture is.
   */
  const open = async (commands: readonly CanvasCommand[] = []): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      savedMembers.value = membership()
      await reopen()
      const now = session.state.value
      loading.value = false
      return commands.length === 0 || !now || await preview({ ...now, commands }, now, false)
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
      return false
    } finally {
      loading.value = false
    }
  }

  const nameOf = (alias: string): string => {
    const geometry = session.drawnPicture.value
    return geometry?.elements.find((one) => one.alias === alias)?.label
      ?? geometry?.boxes.find((one) => one.alias === alias)?.label ?? alias
  }

  /** What Save would write, read off the state against the last save. */
  const changes = computed((): readonly PendingChange[] => {
    const geometry = session.geometry.value
    const now = session.state.value
    const before = saved.value
    if (!geometry || !now || !before) return []
    const model = (now.commands ?? []).map(c => ({
      key: `${c.op}:${c.artifact_id}`, model: true,
      text: c.op === 'model.element.create' ? `Create element: ${c.name}`
        : c.op === 'model.element.rename' ? `Rename element: ${c.name}`
        : c.op === 'model.element.delete' ? `Delete from model: ${c.artifact_id}`
        : `${c.op === 'model.relation.edit' ? 'Edit' : 'Create'} relationship: ${c.artifact_id}`,
    }))
    const added = [...now.additions ?? []].map(([id, name]) => ({ key: id, text: `Added to diagram: ${name}` }))
    const originalAliases = new Set(before.picture?.elements.map(e => e.alias))
    const removed = [...now.removed ?? []].filter(alias => originalAliases.has(alias)).map((alias) => ({
      key: `removed:${alias}`, text: `Removed from the diagram: ${nameOf(alias)} — it stays in the model`,
    }))
    if (!now.byHand) {
      return [...(before.byHand ? [{ key: 'automatic', text: 'Returned to automatic layout' }] : []),
        ...added, ...removed, ...model]
    }
    const reference = referenceOf(geometry, before, now)
    const takenOver: PendingChange[] = before.byHand ? []
      : [{ key: 'by-hand', text: 'Arranged by hand: new elements will be placed beside their neighbours' }]
    return [
      ...added, ...removed, ...model,
      ...takenOver,
      ...arrangedUnits(geometry, reference, now.arrangement).map((alias) => ({
        key: alias, text: `Arranged: ${nameOf(alias)}`,
      })),
    ]
  })

  /** What the session's arranging is counted against: the last save, or the picture it took over. */
  const referenceOf = (geometry: LayoutGeometry, before: ArrangementState, now: ArrangementState): Arrangement =>
    before.byHand ? before.arrangement : (now.takenOver ?? widenedArrangement(geometry, before.arrangement))

  const wanted = (): ArrangedLayout | null => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (!geometry || !now?.byHand) return null
    const layout = layoutOf(geometry, now.arrangement)
    const before = saved.value
    const routed = session.routes.value?.routes
    if (!before || !routed) return layout
    const shown = shownRoutesOfMoved(geometry, referenceOf(geometry, before, now), now.arrangement, routed)
    return { ...layout, relations: { ...shown, ...layout.relations } }
  }

  /** The entity ids the session removed from the diagram, from the picture as drawn. */
  const removedIds = (removed = session.state.value?.removed ?? new Set<string>()): ReadonlySet<string> => {
    return new Set(saved.value?.picture?.elements
      .filter((one) => removed.has(one.alias) && one.key !== undefined)
      .flatMap((one) => (one.key === undefined ? [] : [one.key])) ?? [])
  }

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
    const written = await Effect.runPromise(svc.editDiagram(diagramId(), {
      ...write, ...(state.commands?.length ? { commands: state.commands } : {}),
      layout_patch: layoutPatch,
      dry_run: false,
    }))
    if (!written.wrote) {
      throw new Error(`The diagram was not written: ${written.warnings.join(' ') || 'it was refused'}`)
    }
    savedMembers.value = write
    await reopen()
    onMembershipSaved()
  }

  /** Write what the session changed. Stays in edit mode; what was saved is the new starting point. */
  const save = async (): Promise<boolean> => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (!geometry || !now) return false
    const removed = removedIds()
    if (patchIsEmpty(layoutPatchBetween(stored.value ?? {}, wanted())) && changes.value.length === 0) return true
    saving.value = true
    error.value = null
    try {
      const patch = layoutPatchBetween(stored.value ?? {}, wanted())
      // One write when what the diagram holds changes: membership and layout together, so the stored
      // layout always matches the body that write generates (D12).
      if (removed.size > 0 || now.additions?.size || now.commands?.length || now.overlays?.length) {
        await writeMembership(removed, patch)
        return true
      }
      if (patchIsEmpty(patch)) {
        saved.value = session.state.value
        return true
      }
      const result = await Effect.runPromise(svc.patchLayout(diagramId(), patch, false))
      if (result.errors.length > 0) {
        error.value = result.errors.join(' ')
        return false
      }
      const layout = result.layout.elements || result.layout.boxes ? result.layout : null
      stored.value = layout
      saved.value = session.state.value
      return true
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
      return false
    } finally {
      saving.value = false
    }
  }

  /** Back to the last save, with nothing to undo. */
  const discard = () => {
    const geometry = saved.value?.picture
    if (geometry && saved.value) session.open(geometry, saved.value)
  }

  /** PlantUML's picture again, as one undoable step. */
  const returnToAutomatic = () => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (geometry && now?.byHand) session.step({ ...now, arrangement: drawnArrangement(geometry), byHand: false })
  }

  /**
   * Remove the elements of *aliases* from the diagram, never from the model, as one undoable step. A box
   * among them is not removed: a grouping is the diagram's structure, not an element it draws.
   */
  const remove = (aliases: readonly string[]) => {
    const now = session.state.value
    if (!now) return
    const additions = new Map(now.additions)
    const removed = new Set(now.removed)
    const refused: string[] = []
    for (const alias of aliases) {
      const key = session.geometry.value?.elements.find((one) => one.alias === alias)?.key
      if (key === undefined) continue
      // A further occurrence of an entity is held by the diagram's own records, which this write does not
      // edit yet: refused with a sentence rather than removed on the canvas and quietly kept by Save.
      const added = [...additions].find(([id]) => stableEntityId(id) === stableEntityId(key))
      const member = savedMembers.value?.entity_ids.some((id) => stableEntityId(id) === stableEntityId(key)) ?? false
      if (added) additions.delete(added[0])
      else if (!member) { refused.push(nameOf(alias)); continue }
      removed.add(alias)
    }
    error.value = refused.length === 0 ? null
      : `${refused.join(', ')} ${refused.length === 1 ? 'is a further occurrence' : 'are further occurrences'}; `
        + 'removing one is not possible here yet.'
    if (removed.size > (now.removed?.size ?? 0)) session.step({ ...now, additions, removed })
  }

  const add = async (id: string, name: string, type?: string) => {
    const drawn = savedMembers.value
    const now = session.state.value
    if (!drawn || !now || loading.value || saving.value) return
    const existing = [...session.drawnPicture.value?.elements ?? [], ...saved.value?.picture?.elements ?? []]
      .find(e => e.key === stableEntityId(id))
    if (existing && now.removed?.has(existing.alias)) {
      const removed = new Set(now.removed)
      removed.delete(existing.alias)
      const additions = new Map(now.additions)
      if (!drawn.entity_ids.some(key => stableEntityId(key) === stableEntityId(id))) additions.set(id, name)
      await preview({ ...now, removed, additions }, now)
      return
    }
    if (drawn.entity_ids.some(key => stableEntityId(key) === stableEntityId(id)) || now.additions?.has(id)) return
    const additions = new Map(now.additions).set(id, name)
    await preview({ ...now, additions, addedTypes: type ? new Map(now.addedTypes).set(id, type) : now.addedTypes }, now)
  }

  /** Draw *next*'s content: as one undoable step, or (*undoable* false) as the state the session opens on. */
  const preview = async (next: ArrangementState, previous: ArrangementState, undoable = true) => {
    const drawn = savedMembers.value
    if (!drawn || loading.value || saving.value) return false
    loading.value = true
    error.value = null
    try {
      const { preview: request } = composeCanvas(drawn, next, removedIds(next.removed))
      const carried = wanted()
      const picture = await Effect.runPromise(svc.previewLayoutGeometry(diagramId(), {
        ...request, ...(carried ? {arrangement: carried} : {}),
      }))
      if (session.state.value !== previous) return false
      const arrangement = carried ? arrangedBy(picture, picture.layout ?? carried) : drawnArrangement(picture)
      if (undoable) session.step({ ...next, picture, arrangement })
      else session.open(picture, { ...next, arrangement })
      return true
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
      return false
    } finally {
      loading.value = false
    }
  }

  const propose = async (command: CanvasCommand, overlay?: Record<string, unknown>) => {
    const now = session.state.value
    if (!now) return false
    let commands = [...now.commands ?? []]
    if (command.op === 'model.element.rename' || command.op === 'model.relation.edit') {
      commands = commands.filter(c => c.op !== command.op || c.artifact_id !== command.artifact_id)
    }
    commands.push(command)
    return preview({ ...now, commands, overlays: overlay ? [...now.overlays ?? [], overlay] : now.overlays }, now)
  }

  return { add, propose, session, changes, loading, saving, error, open, save, discard, returnToAutomatic, remove }
}

export type DiagramEditing = ReturnType<typeof useDiagramEditing>
