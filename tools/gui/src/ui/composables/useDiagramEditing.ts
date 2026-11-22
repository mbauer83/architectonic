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
  arrangedBy, arrangedUnits, layoutOf, layoutPatchBetween, patchIsEmpty,
} from '../../domain/layout/arrangementLayout'
import { drawnArrangement } from '../../domain/layout/lab/labArrangement'
import { widenedArrangement } from '../../domain/layout/lab/labRouting'
import type { Membership } from '../../domain/layout/diagramMembership'
import { membershipWithout } from '../../domain/layout/diagramMembership'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ArrangementState } from './useArrangementSession'
import { useArrangementSession } from './useArrangementSession'

/** One row of what Save would write, in the product's words. */
export interface PendingChange {
  readonly key: string
  readonly text: string
}

/** What a diagram draws, as last read: what a membership write starts from. */
export interface DrawnMembership extends Membership {
  readonly diagram_type: string
  readonly name: string
  readonly diagram_entities?: Readonly<Record<string, unknown>>
}

export function useDiagramEditing(
  svc: ModelService, diagramId: () => string, membership: () => DrawnMembership | null,
) {
  const session = useArrangementSession(
    (shapes) => svc.drawResizedShapes(diagramId(), shapes),
    (geometry, automatic) => widenedArrangement(geometry, automatic),
  )
  /** The layout the diagram stored when the session opened or last saved; null while PlantUML arranges it. */
  const stored = shallowRef<StoredLayout | null>(null)
  /** Where the session started from, and where Discard returns to. */
  const saved = shallowRef<ArrangementState | null>(null)
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
    saved.value = savedState(geometry, layout)
    session.open(geometry, carried ? { arrangement: arrangedBy(geometry, carried), byHand: true } : saved.value)
  }

  const open = async (): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      await reopen()
      return true
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
    const removed = [...now.removed ?? []].map((alias) => ({
      key: `removed:${alias}`, text: `Removed from the diagram: ${nameOf(alias)} — it stays in the model`,
    }))
    if (!now.byHand) {
      return [...(before.byHand ? [{ key: 'automatic', text: 'Returned to automatic layout' }] : []), ...removed]
    }
    const reference = before.byHand ? before.arrangement : widenedArrangement(geometry, before.arrangement)
    const takenOver: PendingChange[] = before.byHand ? []
      : [{ key: 'by-hand', text: 'Arranged by hand: new elements will be placed beside their neighbours' }]
    return [
      ...removed,
      ...takenOver,
      ...arrangedUnits(geometry, reference, now.arrangement).map((alias) => ({
        key: alias, text: `Arranged: ${nameOf(alias)}`,
      })),
    ]
  })

  const wanted = (): ArrangedLayout | null => {
    const geometry = session.geometry.value
    const now = session.state.value
    return geometry && now?.byHand ? layoutOf(geometry, now.arrangement) : null
  }

  /** The entity ids the session removed from the diagram, from the picture as drawn. */
  const removedIds = (): ReadonlySet<string> => {
    const removed = session.state.value?.removed ?? new Set<string>()
    return new Set(session.drawnPicture.value?.elements
      .filter((one) => removed.has(one.alias) && one.key !== undefined)
      .flatMap((one) => (one.key === undefined ? [] : [one.key])) ?? [])
  }

  /**
   * Write what the diagram holds less what was removed, through the diagram write, and read the picture
   * it draws now, keeping the arrangement of everything still on it.
   */
  const writeMembership = async (removed: ReadonlySet<string>, arranged: ArrangedLayout | null): Promise<void> => {
    const drawn = membership()
    if (!drawn) throw new Error('The diagram has not been read; reload the page.')
    const kept = membershipWithout(drawn, removed)
    await Effect.runPromise(svc.editDiagram(diagramId(), {
      diagram_type: drawn.diagram_type, name: drawn.name,
      entity_ids: [...kept.entity_ids], connection_ids: [...kept.connection_ids],
      ...(drawn.diagram_entities ? { diagram_entities: { ...drawn.diagram_entities } } : {}),
      ...(kept.authored_groupings ? { authored_groupings: kept.authored_groupings } : {}),
      dry_run: false,
    }))
    await reopen(arranged)
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
      const arranged = wanted()
      if (removed.size > 0) await writeMembership(removed, arranged)
      const patch = layoutPatchBetween(stored.value ?? {}, arranged === null ? null : wanted())
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
    const geometry = session.drawnPicture.value
    if (geometry && saved.value) session.open(geometry, saved.value)
  }

  /** PlantUML's picture again, as one undoable step. */
  const returnToAutomatic = () => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (geometry && now?.byHand) session.step({ ...now, arrangement: drawnArrangement(geometry), byHand: false })
  }

  /** Remove *alias* from the diagram, never from the model, as one undoable step. */
  const remove = (alias: string) => {
    const now = session.state.value
    const element = session.geometry.value?.elements.some((one) => one.alias === alias)
    if (now && element) session.step({ ...now, removed: new Set([...now.removed ?? [], alias]) })
  }

  return { session, changes, loading, saving, error, open, save, discard, returnToAutomatic, remove }
}

export type DiagramEditing = ReturnType<typeof useDiagramEditing>
