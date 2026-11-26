/**
 * An edit session: the arranging session (`useArrangementSession`) over the picture its *source* draws — a
 * stored diagram's, read against what the diagram last stored, or a candidate's (`pictureSource`).
 *
 * Nothing persists until Save, and what Save would write is read off the state, never counted: the
 * arrangement now against the one last saved (`useSessionChanges`). So returning to automatic leaves no
 * arranging change, a move undone leaves none, and the count follows Undo and Redo (owner, F3).
 *
 * Taking a picture over writes it down as a first layout is: PlantUML's arrangement as drawn, its lines
 * kept, the same rule the server's first layout applies.
 */
import { ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { PictureContext } from '../../domain'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import type { ArrangedLayout, StoredLayout } from '../../domain/layout/arrangementLayout'
import {
  arrangedBy, layoutOf, layoutPatchBetween, patchIsEmpty, shownRoutesOfMoved,
} from '../../domain/layout/arrangementLayout'
import { drawnArrangement, placedAt } from '../../domain/layout/lab/labArrangement'
import type { Point } from '../../domain/layout/geometry'
import { occurrenceItems } from '../../domain/diagramOccurrences'
import type { PendingChange } from '../../domain/layout/sessionChanges'
import { addOccurrenceFor } from '../lib/diagramOccurrences'
import { referenceOf, useSessionChanges } from './useSessionChanges'
import type { DrawnMembership } from '../../domain/layout/diagramMembership'
import { membershipOf } from '../../domain/layout/diagramMembership'
import { canvasMembers, composeCanvas, withCommand, withoutDraft } from '../../domain/layout/canvasComposition'
import type { CanvasCommand, GroupingIntent } from '../../ports/diagramWriteBodies'
import type { LayoutPatch } from '../../ports/DiagramLayoutRepository'
import { stableEntityId } from '../../domain/artifactId'
import { type Restack, restacked } from '../../domain/layout/stacking'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ReadingLens } from '../../domain/readingLens'
import type { ArrangementState } from './useArrangementSession'
import { useArrangementSession } from './useArrangementSession'
import { type PictureSource, savedInto } from './pictureSource'

export type { PendingChange }

/** What a page adds to its edit session: told when a save changed what the diagram holds, the lens it
 * reads with, and the diagram's context read, which names the elements the session lists. */
export interface EditingOptions {
  readonly onMembershipSaved?: () => void
  readonly lens?: () => ReadingLens | undefined
  readonly context?: () => PictureContext | null
}

export function useDiagramEditing(
  svc: ModelService, source: PictureSource, membership: () => DrawnMembership | null,
  options: EditingOptions = {},
) {
  const onMembershipSaved = options.onMembershipSaved ?? (() => {})
  const lens = options.lens ?? (() => undefined)
  const session = useArrangementSession((shapes) => source.reshape(shapes))
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
    const geometry = await Effect.runPromise(source.read(lens()))
    const layout = geometry.layout && (geometry.layout.elements || geometry.layout.boxes || geometry.layout.z)
      ? geometry.layout : null
    stored.value = layout
    saved.value = { ...savedState(geometry, layout), picture: geometry }
    session.open(geometry, carried ? { arrangement: arrangedBy(geometry, carried), byHand: true } : saved.value)
  }

  /**
   * Open on the picture as stored; *commands* are content already proposed elsewhere, and *added* model
   * elements already chosen elsewhere, drawn at once and not undoable: they are where the session starts, as
   * the stored picture is.
   */
  const open = async (commands: readonly CanvasCommand[] = [], added = new Map<string, string>()): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      savedMembers.value = membership()
      await reopen()
      const now = session.state.value
      loading.value = false
      return (commands.length === 0 && added.size === 0) || !now
        || await preview({ ...now, commands, ...(added.size ? { additions: added } : {}) }, now, false)
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
      return false
    } finally {
      loading.value = false
    }
  }

  /** Each drawing of *picture* that draws an element, by its name in the model as the session has it. */
  const members = (picture: LayoutGeometry, state: ArrangementState | null) => {
    const context = options.context?.()
    return context ? canvasMembers(context, state, picture) : []
  }
  const { changes, undoStep, redoStep, nameOf } = useSessionChanges(session, saved, {
    members, stated: () => savedMembers.value?.authored_groupings ?? [],
  })

  const wanted = (): ArrangedLayout | null => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (!geometry || !now?.byHand) return null
    const layout = layoutOf(geometry, now.arrangement)
    const before = saved.value
    const routed = session.routes.value?.routes
    if (!before || !routed) return layout
    const shown = shownRoutesOfMoved(geometry, referenceOf(before, now), now.arrangement, routed)
    return { ...layout, relations: { ...shown, ...layout.relations } }
  }

  /** The entity ids the session removed from the diagram, from the picture as drawn. */
  const removedIds = (removed = session.state.value?.removed ?? new Set<string>()): ReadonlySet<string> => {
    return new Set(saved.value?.picture?.elements
      .filter((one) => removed.has(one.alias) && one.key !== undefined)
      .flatMap((one) => (one.key === undefined ? [] : [one.key])) ?? [])
  }

  const diagramId = (): string => savedInto(source)

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
    // Regrouped or with boxes edited, the groupings are the server's to identify: read back what it wrote.
    savedMembers.value = state.regroupings?.length || state.groupings
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
        || now.regroupings?.length || now.occurrences?.length || now.drawnRelations?.length || now.groupings) {
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
   * as the diagram's occurrence statement at Save, one undoable step. *at*, on a picture arranged by hand, is
   * where it is placed; without it the composer places it beside its neighbours.
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

  /** *id* drawn on the diagram, as one undoable step; *at*, on a picture arranged by hand, is where it is placed. */
  const add = async (id: string, name: string, type?: string, at?: Point) => {
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
    const addedTypes = type ? new Map(now.addedTypes).set(id, type) : now.addedTypes
    await preview({ ...now, additions, addedTypes }, now, true, at && [id, at])
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
      const picture = await Effect.runPromise(source.preview(
        { ...request, ...(carried ? {arrangement: carried} : {}) }, lens()))
      if (session.state.value !== previous) return false
      const read = carried ? arrangedBy(picture, picture.layout ?? carried) : drawnArrangement(picture)
      const key = place && stableEntityId(place[0])
      const alias = key && picture.elements.find((one) => stableEntityId(one.key ?? '') === key)?.alias
      // Placed where it was put on a picture arranged by hand; an automatic one is PlantUML's to lay out (D15).
      const arrangement = place && alias && carried ? placedAt(picture, read, new Map([[alias, place[1]]])) : read
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

  /**
   * *proposed* kept in the session as one undoable step, each over what it supersedes (`withCommand`);
   * *place* puts the element it draws at a point on the picture.
   */
  const propose = async (
    proposed: CanvasCommand | readonly CanvasCommand[], overlay?: Record<string, unknown>,
    place?: readonly [string, Point],
  ) => {
    const now = session.state.value
    if (!now) return false
    const commands = [proposed].flat().reduce(withCommand, now.commands ?? [])
    const overlays = overlay ? [...now.overlays ?? [], overlay] : now.overlays
    return preview({ ...now, commands, overlays }, now, true, place)
  }

  /**
   * The relation *id*, which the model holds, drawn on the diagram as one undoable step: diagram content,
   * no model change (03·8, "In the model: draw it"); *overlay* is the label this diagram draws on it.
   */
  const drawRelation = async (id: string, overlay?: Record<string, unknown>) => {
    const now = session.state.value
    if (!now || now.drawnRelations?.includes(id)) return false
    const overlays = overlay ? [...now.overlays ?? [], overlay] : now.overlays
    return preview({ ...now, drawnRelations: [...now.drawnRelations ?? [], id], overlays }, now)
  }

  /** The draft *id* discarded with everything the session proposed about it, as one undoable step. */
  const discardDraft = async (id: string) => {
    const now = session.state.value
    return now ? preview(withoutDraft(now, id), now) : false
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

  /** The content *change* makes of the session's, drawn as one undoable step; nothing where it makes none. */
  const restate = (change: (now: ArrangementState) => ArrangementState | null): Promise<boolean> => {
    const now = session.state.value
    const next = now && change(now)
    return next ? preview(next, now) : Promise.resolve(false)
  }

  return {
    add, propose, session, changes, undoStep, redoStep, nameOf, loading, saving, error, open, save, discard,
    returnToAutomatic, remove, restack, nest, addOccurrence, discardDraft, drawRelation, restate,
    /** The boxes the diagram states, as last read or saved. */
    statedGroupings: (): readonly AuthoredGrouping[] => savedMembers.value?.authored_groupings ?? [],
  }
}

export type DiagramEditing = ReturnType<typeof useDiagramEditing>
