/**
 * What a diagram's edit session would write, read off its state against the last save (owner, F3), and
 * what each step of it did, read off the two states it lies between (`stepName`).
 *
 * Arranging counts one change per element, box or line arranged (sketch 01·6), against the last save or,
 * on a picture still arranged automatically when the session opened, against the picture as it was
 * taken over. Taking the picture over is no change of its own: it is how the first move is written.
 */
import { computed, type ShallowRef } from 'vue'
import { arrangedUnits, linesArranged } from '../../domain/layout/arrangementLayout'
import { stableEntityId } from '../../domain/artifactId'
import type { Arrangement } from '../../domain/layout/lab/labArrangement'
import { widenedArrangement } from '../../domain/layout/lab/labRouting'
import { type PendingChange, contentChanges } from '../../domain/layout/sessionChanges'
import { stepName } from '../../domain/layout/sessionSteps'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ArrangementSession, ArrangementState } from './useArrangementSession'

/** What a session's arranging is counted against: the last save, or the picture it took over. */
export const referenceOf = (geometry: LayoutGeometry, before: ArrangementState, now: ArrangementState): Arrangement =>
  before.byHand ? before.arrangement : (now.takenOver ?? widenedArrangement(geometry, before.arrangement))

export function useSessionChanges(session: ArrangementSession, saved: ShallowRef<ArrangementState | null>) {
  /** The pictures a shape may be named from: the one drawn now, and the one saved, which still draws what
   * the session removed. */
  const pictures = () => [session.drawnPicture.value, saved.value?.picture].flatMap((one) => (one ? [one] : []))
  const nameOf = (alias: string): string => pictures()
    .flatMap((geometry) => [...geometry.elements, ...geometry.boxes])
    .find((one) => one.alias === alias)?.label ?? alias
  /** The alias the pictures draw the entity *id* under; the id itself where they draw none. */
  const aliasOf = (id: string): string => pictures()
    .flatMap((geometry) => geometry.elements.find((one) => one.key === stableEntityId(id))?.alias ?? [])[0] ?? id

  /** What *now* holds that the diagram did not: elements, boxes and model changes. */
  const contentOf = (now: ArrangementState): readonly PendingChange[] => {
    const geometry = session.geometry.value
    return geometry ? contentChanges(
      now, new Set(saved.value?.picture?.elements.map((e) => e.alias)), nameOf, (key) => nameOf(aliasOf(key)),
      (grouping) => geometry.boxes.find((one) => one.key === grouping)?.label ?? grouping,
    ) : []
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
    if (!now.byHand) {
      return [...(before.byHand ? [{ key: 'automatic', text: 'Returned to automatic layout' }] : []), ...content]
    }
    const arranged = arrangedNames(referenceOf(geometry, before, now), now.arrangement)
    return [...content, ...arranged.map(({ key, name }) => ({ key, text: `Arranged: ${name}` }))]
  })

  /** What the step from *before* to *after* did, in the words of the list. */
  const named = (before: ArrangementState, after: ArrangementState): string => {
    const geometry = session.geometry.value
    const samePicture = !before.picture || !after.picture || before.picture === after.picture
    const from = geometry && !before.byHand && after.byHand ? referenceOf(geometry, before, after) : before.arrangement
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
