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
import { drawnArrangement, placedAt } from '../../domain/layout/lab/labArrangement'
import type { Point } from '../../domain/layout/geometry'
import { occurrenceItems } from '../../domain/archimateOccurrences'
import { type PendingChange, contentChanges } from '../../domain/layout/sessionChanges'
import { addOccurrenceFor } from '../lib/archimateOccurrences'
import { widenedArrangement } from '../../domain/layout/lab/labRouting'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { membershipOf } from '../../domain/layout/diagramMembership'
import { composeCanvas, withCommand } from '../../domain/layout/canvasComposition'
import type { CanvasCommand, GroupingIntent } from '../../ports/diagramWriteBodies'
import type { LayoutPatch } from '../../ports/DiagramLayoutRepository'
import { stableEntityId } from '../../domain/artifactId'
import { type Restack, restacked } from '../../domain/layout/stacking'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ReadingLens } from '../../domain/readingLens'
import type { ArrangementState } from './useArrangementSession'
import { useArrangementSession } from './useArrangementSession'

export type { PendingChange }

export function useDiagramEditing(
  svc: ModelService, diagramId: () => string, membership: () => DrawnMembership | null,
  onMembershipSaved: () => void = () => {}, lens: () => ReadingLens | undefined = () => undefined,
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
    const geometry = await Effect.runPromise(svc.readLayoutGeometry(diagramId(), lens()))
    const layout = geometry.layout && (geometry.layout.elements || geometry.layout.boxes || geometry.layout.z)
      ? geometry.layout : null
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
  /** The alias the picture draws the entity *id* under; the id itself where it draws none. */
  const aliasOf = (id: string): string =>
    session.drawnPicture.value?.elements.find((one) => one.key === stableEntityId(id))?.alias ?? id
  /** What Save would write, read off the state against the last save. */
  const changes = computed((): readonly PendingChange[] => {
    const geometry = session.geometry.value
    const now = session.state.value
    const before = saved.value
    if (!geometry || !now || !before) return []
    const content = contentChanges(
      now, new Set(before.picture?.elements.map((e) => e.alias)), nameOf, (key) => nameOf(aliasOf(key)),
      (grouping) => geometry.boxes.find((one) => one.key === grouping)?.label ?? grouping,
    )
    if (!now.byHand) {
      return [...(before.byHand ? [{ key: 'automatic', text: 'Returned to automatic layout' }] : []), ...content]
    }
    const reference = referenceOf(geometry, before, now)
    const takenOver: PendingChange[] = before.byHand ? []
      : [{ key: 'by-hand', text: 'Arranged by hand: new elements will be placed beside their neighbours' }]
    return [
      ...content,
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
    // Regrouped, the groupings are the server's to compile: read back what it wrote, never restated here.
    savedMembers.value = state.regroupings?.length
      ? membershipOf(await Effect.runPromise(svc.getDiagram(diagramId()))) : write
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
      if (removed.size > 0 || now.additions?.size || now.commands?.length || now.overlays?.length
        || now.regroupings?.length || now.occurrences?.length) {
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
      const layout = result.layout.elements || result.layout.boxes || result.layout.z ? result.layout : null
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
    let occurrences = now.occurrences ?? []
    for (const alias of aliases) {
      const key = session.geometry.value?.elements.find((one) => one.alias === alias)?.key
      if (key === undefined) continue
      // A further drawing added in this session is simply not added; any other is removed by its own id.
      if (occurrences.some((one) => one.id === key)) {
        occurrences = occurrences.filter((one) => one.id !== key)
        continue
      }
      const added = [...additions].find(([id]) => stableEntityId(id) === stableEntityId(key))
      const member = savedMembers.value?.entity_ids.some((id) => stableEntityId(id) === stableEntityId(key))
        || occurrenceItems(savedMembers.value?.diagram_entities ?? {}).some((one) => one.id === key)
      if (added) additions.delete(added[0])
      else if (!member) continue
      removed.add(alias)
    }
    if (removed.size > (now.removed?.size ?? 0) || occurrences.length < (now.occurrences?.length ?? 0)) {
      session.step({ ...now, additions, removed, occurrences })
    }
  }

  /**
   * *entity*, already on the diagram, drawn once more (03·5): a further drawing with its own id, written
   * as the diagram's occurrence statement at Save, one undoable step. *at*, on the picture, is where it
   * is placed; without it the composer places it beside its neighbours.
   */
  const addOccurrence = async (entity: { artifact_id: string; name: string; display_alias: string }, at?: Point) => {
    const drawn = savedMembers.value
    const now = session.state.value
    if (!drawn || !now) return false
    const stated = {
      ...drawn.diagram_entities,
      occurrence: [...occurrenceItems(drawn.diagram_entities ?? {}), ...now.occurrences ?? []],
    }
    const { occurrenceId } = addOccurrenceFor(stated, entity)
    const occurrence = { id: occurrenceId, backing_entity_id: entity.artifact_id }
    return preview({ ...now, occurrences: [...now.occurrences ?? [], occurrence] }, now, true, at && [occurrenceId, at])
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
  const preview = async (
    next: ArrangementState, previous: ArrangementState, undoable = true, place?: readonly [string, Point],
  ) => {
    const drawn = savedMembers.value
    if (!drawn || loading.value || saving.value) return false
    loading.value = true
    error.value = null
    try {
      const { preview: request } = composeCanvas(drawn, next, removedIds(next.removed))
      const carried = wanted()
      const picture = await Effect.runPromise(svc.previewLayoutGeometry(
        diagramId(), { ...request, ...(carried ? {arrangement: carried} : {}) }, lens()))
      if (session.state.value !== previous) return false
      const read = carried ? arrangedBy(picture, picture.layout ?? carried) : drawnArrangement(picture)
      const alias = place && picture.elements.find((one) => one.key === place[0])?.alias
      const arrangement = place && alias ? placedAt(picture, read, new Map([[alias, place[1]]])) : read
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

  /** *proposed* kept in the session as one undoable step, each over what it supersedes (`withCommand`). */
  const propose = async (proposed: CanvasCommand | readonly CanvasCommand[], overlay?: Record<string, unknown>) => {
    const now = session.state.value
    if (!now) return false
    const commands = [proposed].flat().reduce(withCommand, now.commands ?? [])
    return preview({ ...now, commands, overlays: overlay ? [...now.overlays ?? [], overlay] : now.overlays }, now)
  }

  /**
   * The element *alias* moved into the diagram's own box *box*, or out of the box it is in (*box* null),
   * as one undoable step the server compiles (`GroupingIntent`). A box grows round what it holds, so
   * the element is drawn inside the box it joins wherever it stood.
   */
  const nest = async (alias: string, box: string | null) => {
    const now = session.state.value
    const drawn = session.geometry.value
    const key = drawn?.elements.find((one) => one.alias === alias)?.key
    const into = box === null ? undefined : drawn?.boxes.find((one) => one.alias === box)?.key
    if (!now || !drawn || key === undefined || (box !== null && into === undefined)) return false
    const intent: GroupingIntent = into === undefined
      ? { intent: 'unnest', keys: [key] } : { intent: 'nest', keys: [key], grouping: into }
    return preview({ ...now, regroupings: [...now.regroupings ?? [], intent] }, now)
  }

  /** The shapes *aliases* restacked among their siblings (`stacking`), as one undoable step. */
  const restack = (aliases: readonly string[], how: Restack) =>
    session.change((geometry, now, where) => restacked(geometry, now, where, aliases, how))

  return {
    add, propose, session, changes, loading, saving, error, open, save, discard, returnToAutomatic, remove, restack,
    nest, addOccurrence,
  }
}

export type DiagramEditing = ReturnType<typeof useDiagramEditing>
