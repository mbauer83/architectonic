/**
 * What the stress workspace's canvas says it shows: the caption under the picture, and what is said where
 * there is no picture. While an architecture is judged against the test set, the caption names that
 * architecture, by name, from the moment it is chosen — never the naive architecture while another is judged.
 */
import type { WorkspaceTab } from './analysisProgress'
import { INTEGRATION, NAIVE } from './testSet'

export interface CanvasReading {
  readonly tab: WorkspaceTab
  /** The stressor row in focus on the Stressors tab. */
  readonly selected: string | null
  /** The architecture judged against the test set: `naive`, `integration`, a candidate's id, or none. */
  readonly judging: string | null
  /** The name of the candidate being judged, where one is. */
  readonly judgedName: string
  /** Whether the judged candidate's comparison has been read, so the picture is the candidate's. */
  readonly judgedRead: boolean
}

const GESTURES = 'Scroll to zoom · Drag to pan'

/** The caption under the canvas for *reading*. */
export const canvasCaption = (reading: CanvasReading): string => {
  const { tab, selected, judging } = reading
  if (judging === INTEGRATION) return `The integration is the model as the integrated candidates left it · ${GESTURES}`
  if (judging === NAIVE) return `The naive architecture, being judged · ${GESTURES}`
  if (judging) {
    return reading.judgedRead
      ? `${reading.judgedName}, being judged · marked with what it changes from the naive · ${GESTURES}`
      : `${reading.judgedName}, being judged · drawing it…`
  }
  if (tab === 'stressors' && selected) return `Press an element to tick or untick it for ${selected} · ${GESTURES}`
  return tab === 'stressors'
    ? `Select a row, or an element to mark the rows that tick it · ${GESTURES}`
    : `Select a row or an element · ${GESTURES}`
}

/** What the canvas says where there is no picture for *reading*. */
export const emptyCaption = (reading: CanvasReading): string =>
  reading.judging && reading.judging !== NAIVE && reading.judging !== INTEGRATION
    ? `Drawing ${reading.judgedName}…`
    : 'Nothing to draw yet: sketch the naive architecture to define it.'
