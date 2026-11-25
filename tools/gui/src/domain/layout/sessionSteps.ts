/**
 * What one step of a canvas session did, named in the words of the list Save shows (sketch 01·6), so
 * Undo's and Redo's tooltips can say which step they take back or do again.
 *
 * A step is read off the two states it lies between, never recorded beside them: the rows of what Save
 * would write before and after it, and what it arranged. So a step names what it changed whichever way
 * it is walked, and a step that removed an element says, as the list does, that it stays in the model.
 */
import type { PendingChange } from './sessionChanges'

/** The two sides of one step, as the session reads them. */
export interface Step {
  /** The step gave the picture back to the automatic layout. */
  readonly returnedToAutomatic: boolean
  /** What Save would write before the step, and after it. */
  readonly before: readonly PendingChange[]
  readonly after: readonly PendingChange[]
  /** What the step itself arranged, by name: elements, boxes and lines. */
  readonly arranged: readonly string[]
}

const same = (one: PendingChange, other: PendingChange): boolean => one.key === other.key && one.text === other.text

/** The first of *texts*, and how many more there are. */
const summed = (texts: readonly string[]): string =>
  texts.length === 1 ? texts[0] : `${texts[0]} and ${texts.length - 1} more`

/** The step's name: what it added to the list, else what it took off it, else what it arranged. */
export const stepName = (step: Step): string => {
  if (step.returnedToAutomatic) return 'Return to automatic layout'
  const added = step.after.filter((row) => !step.before.some((was) => same(was, row)))
  if (added.length) return summed(added.map((row) => row.text))
  const taken = step.before.filter((row) => !step.after.some((now) => same(now, row)))
  if (taken.length) return `Take back ${summed(taken.map((row) => row.text))}`
  return step.arranged.length ? `Arranged: ${summed(step.arranged)}` : 'the last change'
}

/** The rows of what Save would write that go to the model, and those that go to this diagram only. */
export const byWhatTheyChange = (rows: readonly PendingChange[]) => ({
  model: rows.filter((row) => row.model),
  diagram: rows.filter((row) => !row.model),
})
