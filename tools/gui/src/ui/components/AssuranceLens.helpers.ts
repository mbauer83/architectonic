/**
 * Pure helper for AssuranceLens: process the raw arch-lens API response.
 * Extracted here so the stateless logic is testable without mounting the component.
 */

export interface LensNode {
  node_id: string
  node_type: string
  name: string
  tlp?: string
  status?: string
}

/**
 * This element's failure-mode row, rolled up. Absent when the element is not a candidate at all —
 * which is different from being a candidate with nothing found, and must render differently.
 */
export interface FailureModeSummary {
  worst_action_priority: string | null
  high_count: number
  unanswered_cells: number
  nominated_by: string[]
}

export interface LensResult {
  locked: boolean
  visible: boolean
  nodes: LensNode[]
  count: number
  visibilityLimited: boolean
  failureModes: FailureModeSummary | null
}

export interface RawLensResponse {
  locked: boolean
  nodes: LensNode[]
  count: number
  visibility_limited?: boolean
  failure_mode_summary?: FailureModeSummary | null
}

/** Parse a raw lens API response into a typed, display-ready result. */
export function parseLensResponse(raw: RawLensResponse): LensResult {
  return {
    locked: raw.locked,
    visible: !raw.locked && raw.count > 0,
    nodes: raw.locked ? [] : raw.nodes,
    count: raw.locked ? 0 : raw.count,
    visibilityLimited: raw.visibility_limited ?? false,
    failureModes: raw.locked ? null : (raw.failure_mode_summary ?? null),
  }
}

/**
 * One line answering "is there anything here for me". Names the state rather than scoring it, and
 * says plainly when the element has simply not been examined — an unexamined component must not
 * read as a quiet one.
 */
export function failureModeHeadline(summary: FailureModeSummary): string {
  const unanswered = summary.unanswered_cells
  if (summary.worst_action_priority === null) {
    return unanswered > 0
      ? `Not yet examined for failure modes (${unanswered} of 5 guidewords unanswered)`
      : 'Examined for failure modes; none recorded'
  }
  const priority = `worst action priority ${summary.worst_action_priority}`
  const high = summary.high_count > 0 ? `, ${summary.high_count} at high` : ''
  const remaining = unanswered > 0 ? `, ${unanswered} unanswered` : ''
  return `Failure modes: ${priority}${high}${remaining}`
}

/** Whether this element's roll-up is worth drawing attention to. */
export function failureModeNeedsAttention(summary: FailureModeSummary): boolean {
  return summary.high_count > 0 || summary.unanswered_cells > 0
}

/** Build the assurance browse link for a given node. */
export function standaloneNodeLink(nodeId: string): string {
  return `/assurance/node/${encodeURIComponent(nodeId)}`
}
