/**
 * What a diagram's edit session would write, read off its state against the last save (owner, F3), and
 * what each step of it did, read off the two states it lies between (`stepName`).
 *
 * The list names each change to what the diagram holds and to the model, and arranging only as the fact
 * that the layout changed (owner, 2026-11-25): one row, however many shapes and lines moved, read against
 * the last save or, on a picture still arranged automatically when the session opened, against the
 * picture as it was taken over. Taking the picture over is no change of its own. Undo and Redo still name
 * what each step arranged (`stepName`).
 */
import { computed, type ShallowRef } from 'vue'
import { arrangedUnits, linesArranged } from '../../domain/layout/arrangementLayout'
import { stableEntityId } from '../../domain/artifactId'
import type { Arrangement } from '../../domain/layout/lab/labArrangement'
import { type PendingChange, contentChanges } from '../../domain/layout/sessionChanges'
import { stepName } from '../../domain/layout/sessionSteps'
import { boxChanges } from '../../domain/layout/canvasBoxes'
import type { AuthoredGrouping } from '../../domain/authoredGrouping'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ArrangementSession, ArrangementState } from './useArrangementSession'

/** The one row arranging adds to the list, whatever was arranged. */
export const LAYOUT_CHANGED: PendingChange = { key: 'layout', text: 'Layout changed' }

/** What a session's arranging is counted against: the last save, or the picture it took over. */
export const referenceOf = (before: ArrangementState, now: ArrangementState): Arrangement =>
  before.byHand ? before.arrangement : (now.takenOver ?? before.arrangement)

/** The drawings of *picture* that draw an element, with the element's name in the model. */
export type MembersOf = (
  picture: LayoutGeometry, state: ArrangementState | null,
) => readonly { readonly alias: string; readonly name: string }[]

/** What the session's changes are named and counted against beyond its own state. */
export interface SessionReads {
  /** Names a drawing by its element's name, as the model and the session have it; a shape it does not
   * name — a box, or any shape when no names are given — goes by the label the picture draws. */
  readonly members?: MembersOf
  /** The boxes the diagram states, which a session's boxes are counted against. */
  readonly stated?: () => readonly AuthoredGrouping[]
}

export function useSessionChanges(
  session: ArrangementSession, saved: ShallowRef<ArrangementState | null>, reads: SessionReads = {},
) {
  const members = reads.members ?? (() => [])
  /** The pictures a shape may be named from: the one drawn now, and the one saved, which still draws what
   * the session removed. */
  const pictures = () => [session.drawnPicture.value, saved.value?.picture].flatMap((one) => (one ? [one] : []))
  const nameOf = (alias: string): string => pictures()
    .flatMap((geometry) => members(geometry, session.state.value)).find((one) => one.alias === alias)?.name
    ?? pictures().flatMap((geometry) => [...geometry.elements, ...geometry.boxes])
      .find((one) => one.alias === alias)?.label ?? alias
  /** The alias the pictures draw the entity *id* under; the id itself where they draw none. */
  const aliasOf = (id: string): string => pictures()
    .flatMap((geometry) => geometry.elements.find((one) => one.key === stableEntityId(id))?.alias ?? [])[0] ?? id

  /** What *now* holds that the diagram did not: elements, boxes and model changes. */
  const contentOf = (now: ArrangementState): readonly PendingChange[] => {
    const geometry = session.geometry.value
    const boxes = now.groupings ? boxChanges(reads.stated?.() ?? [], now.groupings, saved.value?.picture) : []
    return geometry ? [...contentChanges(
      now, new Set(saved.value?.picture?.elements.map((e) => e.alias)), nameOf, (key) => nameOf(aliasOf(key)),
      (grouping) => geometry.boxes.find((one) => one.key === grouping)?.label ?? grouping,
    ), ...boxes] : []
  }

  /** The names of what was arranged from *before* to *after* on the picture shown now: shapes and lines. */
  const arrangedNames = (before: Arrangement, after: Arrangement): readonly { key: string; name: string }[] => {
    const geometry = session.geometry.value
    if (!geometry) return []
    const lines = linesArranged(geometry, before, after).flatMap((index) => {
      const line = geometry.relations.find((one) => one.index === index)
      return line ? [{ key: `line:${index}`, name: `the line ${nameOf(line.source)} → ${nameOf(line.target)}` }] : []
    })
    return [...arrangedUnits(geometry, before, after).map((alias) => ({ key: alias, name: nameOf(alias) })), ...lines]
  }

  /** What Save would write, read off the state against the last save. */
  const changes = computed((): readonly PendingChange[] => {
    const geometry = session.geometry.value
    const now = session.state.value
    const before = saved.value
    if (!geometry || !now || !before) return []
    const content = contentOf(now)
    const layoutChanged = now.byHand
      ? arrangedNames(referenceOf(before, now), now.arrangement).length > 0 : before.byHand
    return [...content, ...(layoutChanged ? [LAYOUT_CHANGED] : [])]
  })

  /** What the step from *before* to *after* did, in the words of the list. */
  const named = (before: ArrangementState, after: ArrangementState): string => {
    const geometry = session.geometry.value
    const samePicture = !before.picture || !after.picture || before.picture === after.picture
    const from = geometry && !before.byHand && after.byHand ? referenceOf(before, after) : before.arrangement
    return stepName({
      returnedToAutomatic: before.byHand && !after.byHand,
      before: contentOf(before),
      after: contentOf(after),
      arranged: samePicture ? arrangedNames(from, after.arrangement).map(({ name }) => name) : [],
    })
  }

  /** The step Undo would take back, and the one Redo would do again; null where there is none. */
  const undoStep = computed((): string | null => {
    const [before, now] = [session.history.value.at(-1), session.state.value]
    return before && now ? named(before, now) : null
  })
  const redoStep = computed((): string | null => {
    const [now, after] = [session.state.value, session.future.value[0]]
    return now && after ? named(now, after) : null
  })

  return { changes, undoStep, redoStep, nameOf, aliasOf }
}
