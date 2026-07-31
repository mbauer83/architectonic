/**
 * What the architecture graph says the analysis has not reached.
 *
 * These elements deliberately do not get matrix rows. Nominating them produced a hundred blank rows
 * beside the handful the analysis had actually reached, which is the death march the method is
 * scoped to avoid. The claim is still worth making — it is the one thing the graph knows and the
 * analysis cannot — so it is made here, as something to act on rather than as work already queued.
 *
 * Acting on one means adding that element to a control structure deliberately, at which point it
 * becomes a row like any other.
 */

import type { components } from '../../domain/schemas/openapi.generated'

/** The verification finding codes this panel is about.
 *
 * Named rather than inferred from the message: a code is the stable identity of a rule, and matching
 * on wording would silently stop working the first time a message is reworded.
 */
export const LOAD_BEARING_UNANALYSED = 'W511'

/** One finding as `GET /api/assurance/verify` serves it.
 *
 * The served schema rather than a hand-written copy of it: the copy had `subject_name` optional where
 * the route always sends it, so this panel carried a fallback for a case the server does not produce —
 * the drift a restated contract accumulates, and what typing the response is for.
 */
export type VerificationIssue = components['schemas']['AssuranceVerificationIssue']

export interface StructuralGap {
  elementId: string
  /** `TYPE: Name`, or the bare id when the model cannot describe the element. */
  heading: string
  /** The id, shown beneath the heading — or '' when it is already the heading. */
  subheading: string
  message: string
  witness: string[]
}

/**
 * The type abbreviation an artifact id already carries.
 *
 * `REQ@1777369067.3cJ1Yi` → `REQ`. Read off the id rather than fetched: the prefix *is* the type
 * abbreviation, so asking the architecture repository for something the id states would be a second
 * source for one fact.
 */
export function typeAbbreviation(elementId: string): string {
  const [prefix] = elementId.split('@')
  return prefix && prefix !== elementId ? prefix : ''
}

/**
 * How one gap names its element: `TYPE: Name`, with the id demoted to a second line.
 *
 * The list showed a hundred bare artifact ids, each followed by a sentence that repeated the id —
 * so the one thing a reader needed, which element this is, was the one thing absent. The id is
 * demoted rather than dropped: it is what someone quotes when they go and act on the finding.
 */
export function gapHeading(elementId: string, name: string): { heading: string; subheading: string } {
  const trimmed = name.trim()
  if (!trimmed) return { heading: elementId, subheading: '' }
  const abbreviation = typeAbbreviation(elementId)
  return {
    heading: abbreviation ? `${abbreviation}: ${trimmed}` : trimmed,
    subheading: elementId,
  }
}

/** The load-bearing-but-unanalysed findings, strongest first.
 *
 * Ordered by how much relies on the element, because that is the order someone deciding what to
 * analyse next would want and the panel would otherwise present a hundred equals. Ties fall back to
 * the id so the list is stable between reloads rather than shuffling under the reader.
 */
export function structuralGaps(issues: readonly VerificationIssue[]): StructuralGap[] {
  return issues
    .filter((issue) => issue.code === LOAD_BEARING_UNANALYSED)
    .map((issue) => ({
      elementId: issue.node_id,
      ...gapHeading(issue.node_id, issue.subject_name),
      message: issue.message,
      witness: issue.witness,
    }))
    .sort((a, b) => b.witness.length - a.witness.length || a.elementId.localeCompare(b.elementId))
}

/**
 * What this panel is and what to do with it, in two sentences.
 *
 * It said only "107 load-bearing elements no analysis has reached", which tells a reader neither what
 * "load-bearing" means here nor why they should care. Both have to be said: the finding asks someone
 * to act on a claim the *graph* makes and they did not, so it has to explain itself or be ignored.
 */
export const GAPS_EXPLANATION =
  'Components, services and functions that several other elements depend on, and that no '
  + 'failure-mode analysis has looked at yet. They get no matrix rows on purpose — nominating every '
  + 'one would bury the analysis you have actually done — so read this as a shortlist for "what '
  + 'should we look at next". Add one to a control structure and it gets a row.'

/** A count line that says what the list is, and does not imply it is a backlog.
 *
 * "Not yet analysed" rather than "outstanding": these were never promised, and a reader who takes
 * them as queued work has been misled about the size of what they are doing.
 */
export function gapSummary(gaps: readonly StructuralGap[]): string {
  if (gaps.length === 0) {
    return 'Every element the graph shows to be load-bearing has been reached by an analysis.'
  }
  const noun = gaps.length === 1 ? 'element' : 'elements'
  return `${gaps.length} load-bearing ${noun} no analysis has reached, most-relied-on first.`
}
