/**
 * What the stress-analysis workspace marks on the canvas beyond a candidate's comparison: what a
 * focused stressor or end state hits. The marks themselves are the canvas's (`candidates/canvasMarks`).
 * The other way round, an element selected on the canvas marks the stressor rows that tick it (06·1).
 */
import type { Marks } from '../candidates/canvasMarks'
import { stableEntityId } from '../artifactId'

/** The stressors that tick the element *stableId* (as the drawing keys it); none for none selected. */
export const stressorsTicking = (
  ticks: readonly { readonly stressor: string; readonly component: string }[], stableId: string | null,
): ReadonlySet<string> => new Set(stableId === null ? []
  : ticks.filter((tick) => stableEntityId(tick.component) === stableId).map((tick) => tick.stressor))

/** Each component the focus hits, tagged with how many of the focused stressors hit it. */
export const hitMarks = (hitsByStressor: ReadonlyMap<string, readonly string[]>): Marks => {
  const counts = new Map<string, number>()
  for (const hits of hitsByStressor.values()) {
    for (const hit of new Set(hits)) counts.set(hit, (counts.get(hit) ?? 0) + 1)
  }
  const of = hitsByStressor.size
  return new Map([...counts].map(([id, count]) => [stableEntityId(id), {
    kind: 'hit' as const,
    tag: of > 1 ? `hit by ${count} of ${of}` : 'hit',
    title: of > 1 ? `Hit by ${count} of the ${of} stressors in focus` : 'Hit by the stressor in focus',
  }]))
}
