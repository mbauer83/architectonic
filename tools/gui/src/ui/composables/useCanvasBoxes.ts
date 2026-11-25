/**
 * The diagram's boxes edited on its canvas (D9, A-02.39), each edit one undoable step of the session:
 * a box renamed or deleted — never what it holds — a type box added inside one, a new listed box round a
 * selection, and every layer and type box given back to the renderer. What each edit makes of the
 * groupings is `canvasBoxes`'s; this reads the session and steps it.
 */
import { computed } from 'vue'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import {
  type Trail, ownedBoxes, renamedBox, statesRuledBoxes, trailOf, withNewBox, withTypeBox, withoutBox,
  withoutRuledBoxes,
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

  return {
    /** Whether the diagram's layer and type boxes are its own, so *Return to automatic boxes* has work. */
    owned: computed(() => statesRuledBoxes(boxesNow())),
    rename: (alias: string, label: string) => edit(alias, (owned, trail) => renamedBox(owned, trail, label)),
    remove: (alias: string) => edit(alias, withoutBox),
    addTypeBox: (alias: string, type: string, label: string) =>
      edit(alias, (owned, trail) => withTypeBox(owned, trail, type, label)),
    /** Every ruled box dropped: the renderer computes the layer and type boxes again. */
    automatic: () => editing.restate((now) =>
      (statesRuledBoxes(boxesNow()) ? { ...now, groupings: withoutRuledBoxes(boxesNow()) } : null)),
    /** A new listed box labelled *label* round the elements *aliases*. */
    newBox: (aliases: readonly string[], label: string) => editing.restate((now) => {
      const keys = (editing.session.geometry.value?.elements ?? [])
        .flatMap((one) => (aliases.includes(one.alias) && one.key !== undefined ? [one.key] : []))
      return keys.length && label.trim() ? { ...now, groupings: withNewBox(boxesNow(), keys, label.trim()) } : null
    }),
  }
}

export type CanvasBoxes = ReturnType<typeof useCanvasBoxes>
