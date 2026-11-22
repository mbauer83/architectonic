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
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ArrangementState } from './useArrangementSession'
import { useArrangementSession } from './useArrangementSession'

/** One row of what Save would write, in the product's words. */
export interface PendingChange {
  readonly key: string
  readonly text: string
}

export function useDiagramEditing(svc: ModelService, diagramId: () => string) {
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

  const open = async (): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      const geometry = await Effect.runPromise(svc.readLayoutGeometry(diagramId()))
      const layout = geometry.layout && (geometry.layout.elements || geometry.layout.boxes) ? geometry.layout : null
      stored.value = layout
      saved.value = savedState(geometry, layout)
      session.open(geometry, saved.value)
      return true
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
      return false
    } finally {
      loading.value = false
    }
  }

  const nameOf = (alias: string): string => {
    const geometry = session.geometry.value
    return geometry?.elements.find((one) => one.alias === alias)?.label
      ?? geometry?.boxes.find((one) => one.alias === alias)?.label ?? alias
  }

  /** What Save would write, read off the state against the last save. */
  const changes = computed((): readonly PendingChange[] => {
    const geometry = session.geometry.value
    const now = session.state.value
    const before = saved.value
    if (!geometry || !now || !before) return []
    if (!now.byHand) return before.byHand ? [{ key: 'automatic', text: 'Returned to automatic layout' }] : []
    const reference = before.byHand ? before.arrangement : widenedArrangement(geometry, before.arrangement)
    const takenOver: PendingChange[] = before.byHand ? []
      : [{ key: 'by-hand', text: 'Arranged by hand: new elements will be placed beside their neighbours' }]
    return [
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

  /** Write what the session changed. Stays in edit mode; what was saved is the new starting point. */
  const save = async (): Promise<boolean> => {
    const geometry = session.geometry.value
    const now = session.state.value
    if (!geometry || !now) return false
    const patch = layoutPatchBetween(stored.value ?? {}, wanted())
    if (patchIsEmpty(patch) && changes.value.length === 0) return true
    saving.value = true
    error.value = null
    try {
      const result = await Effect.runPromise(svc.patchLayout(diagramId(), patch, false))
      if (result.errors.length > 0) {
        error.value = result.errors.join(' ')
        return false
      }
      const layout = result.layout.elements || result.layout.boxes ? result.layout : null
      stored.value = layout
      saved.value = now
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
    const geometry = session.geometry.value
    if (geometry && saved.value) session.open(geometry, saved.value)
  }

  /** PlantUML's picture again, as one undoable step. */
  const returnToAutomatic = () => {
    const geometry = session.geometry.value
    if (geometry && session.state.value?.byHand) session.step({ arrangement: drawnArrangement(geometry), byHand: false })
  }

  return { session, changes, loading, saving, error, open, save, discard, returnToAutomatic }
}

export type DiagramEditing = ReturnType<typeof useDiagramEditing>
