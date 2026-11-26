/**
 * The diagram's boxes edited on its canvas (D9, A-02.39), each edit one undoable step of the session:
 * a box renamed or deleted — never what it holds — a type box added inside one, a new listed box round a
 * selection, and every box given back as the renderer draws it. What each edit makes of the groupings
 * and the arrangement is `canvasBoxes`'s; this reads the session and steps it.
 */
import { computed } from 'vue'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import {
  type Trail, boxesArranged, boxesDiffer, groupingsDiffer, ownedBoxes, renamedBox, trailOf, withBoxesReturned,
  withNewBox, withTypeBox, withoutBox, withoutRuledBoxes,
} from '../../domain/layout/canvasBoxes'
import type { DiagramEditing } from './useDiagramEditing'

export function useCanvasBoxes(editing: DiagramEditing) {
  /** The boxes as the session has them: its own once it edited one, else the diagram's. */
  const boxesNow = (): readonly AuthoredGrouping[] =>
    editing.session.state.value?.groupings ?? editing.statedGroupings()

  /** The box *alias* changed by *change*, the computed boxes written down first. */
  const edit = (alias: string, change: (owned: readonly AuthoredGrouping[], trail: Trail) => AuthoredGrouping[]) =>
    editing.restate((now) => {
      const picture = editing.session.geometry.value
      const owned = picture ? ownedBoxes(boxesNow(), picture) : null
      const trail = owned && picture ? trailOf(owned, picture, alias) : null
      return owned && trail ? { ...now, groupings: change(owned, trail) } : null
    })

  /** The boxes the session moved or sized, against what its arranging is counted against. */
  const arranged = (): readonly string[] => {
    const [geometry, reference] = [editing.session.geometry.value, editing.reference()]
    const now = editing.session.state.value
    return geometry && reference && now?.byHand ? boxesArranged(geometry, reference, now.arrangement) : []
  }

  /**
   * Every box as the renderer draws it: the groupings as the diagram states them less every ruled one (one
   * step), then the boxes moved or sized back where they were (another), each only where it has work. In
   * that order, because the picture drawn again for the groupings keeps every box at the size it stood —
   * a box widened for a longer title stays wide until it is put back.
   */
  const automatic = async (): Promise<void> => {
    const stated = editing.statedGroupings()
    if (groupingsDiffer(stated, editing.session.state.value?.groupings)) {
      await editing.restate((state) => ({ ...state, groupings: withoutRuledBoxes(stated) }))
    }
    const reference = editing.reference()
    if (reference && arranged().length > 0) {
      editing.session.change((geometry, now) => withBoxesReturned(geometry, reference, now))
    }
  }

  return {
    /** Whether the session's boxes differ from the automatic ones, so *Return to automatic boxes* has work. */
    differs: computed(() => {
      const state = editing.session.state.value
      return boxesDiffer(
        editing.statedGroupings(), state?.groupings, editing.session.geometry.value, editing.reference(),
        state?.byHand ? state.arrangement : null,
      )
    }),
    rename: (alias: string, label: string) => edit(alias, (owned, trail) => renamedBox(owned, trail, label)),
    remove: (alias: string) => edit(alias, withoutBox),
    addTypeBox: (alias: string, type: string, label: string) =>
      edit(alias, (owned, trail) => withTypeBox(owned, trail, type, label)),
    automatic,
    /** A new listed box labelled *label* round the elements *aliases*. */
    newBox: (aliases: readonly string[], label: string) => editing.restate((now) => {
      const keys = (editing.session.geometry.value?.elements ?? [])
        .flatMap((one) => (aliases.includes(one.alias) && one.key !== undefined ? [one.key] : []))
      return keys.length && label.trim() ? { ...now, groupings: withNewBox(boxesNow(), keys, label.trim()) } : null
    }),
  }
}

export type CanvasBoxes = ReturnType<typeof useCanvasBoxes>
