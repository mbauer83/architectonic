import type { ViewpointDefinitionEnvelope } from '../../domain'

/**
 * Whole catalogue rows, built from the contract.
 *
 * Five test modules each wrote their own partial envelope with `query_summary: null` and
 * `fork_status: null` — a shape the route stopped sending when the definition language got a
 * contract, because that response omits what is not set rather than nulling it. Building from one
 * factory means the next field the envelope gains is a compile error here and nowhere else.
 *
 * `definition_digest` and `broken_references` are always sent, so they are always present.
 */
export const viewpointEnvelope = (
  overrides: Partial<ViewpointDefinitionEnvelope> = {},
): ViewpointDefinitionEnvelope => ({
  slug: 'sample',
  version: 1,
  name: 'Sample',
  purpose: 'informing',
  content: 'overview',
  tier: 'module',
  scope_summary: { unrestricted: true },
  definition_digest: 'sha256:sample',
  broken_references: [],
  ...overrides,
})

/** An empty entity-criteria group: a query with no filter still says so, because an absent tree
 * and one that matches everything are different claims. */
export const EMPTY_CRITERIA = { kind: 'group', conjunction: 'and', children: [] } as const
