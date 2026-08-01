import type { DiagramViewpointProjection, ProjectedOccurrence, ViewpointProjection } from '../../../domain'

/**
 * Whole projection rows, built from the contract rather than from whichever fields a test
 * happened to read.
 *
 * Five test modules each wrote their own six-key literal against a fourteen-field row, and
 * they all passed because the decoder declared six fields too — the server had been sending
 * a derived connection's certainty, hop count and witness ids to a client that dropped them
 * on decode. Building from one factory here means the next field the contract gains is a
 * compile error in one place instead of a silent gap in five.
 */

export const occurrence = (overrides: Partial<ProjectedOccurrence> = {}): ProjectedOccurrence => ({
  item_id: 'X@1.a.x',
  item_kind: 'entity',
  state: 'visible',
  membership: 'primary',
  reasons: [],
  style: {},
  connection_type: null,
  source_id: null,
  target_id: null,
  certainty: null,
  hops: null,
  via_connection_ids: [],
  derived_match_hops: null,
  column_values: null,
  ...overrides,
})

export const repositoryProjection = (
  overrides: Partial<ViewpointProjection> = {},
): ViewpointProjection => ({
  applied: true,
  index_generation: 1,
  target: 'repository',
  items: [],
  stale_pin: false,
  warnings: [],
  scale_legends: [],
  rule_outcomes: [],
  ...overrides,
})

export const diagramProjection = (
  items: readonly ProjectedOccurrence[],
  overrides: { target?: 'diagram' | 'matrix'; stale_pin?: boolean } = {},
): DiagramViewpointProjection => ({
  applied: true,
  target: overrides.target ?? 'diagram',
  items,
  stale_pin: overrides.stale_pin ?? false,
  warnings: [],
  scale_legends: [],
  rule_outcomes: [],
})
