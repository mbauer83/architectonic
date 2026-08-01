import { Schema } from 'effect'
import { describe, expect, it } from 'vitest'
import { ProjectedOccurrenceSchema } from './viewpoints'

/** The fields every row carries, spelled out rather than defaulted: this is the decoder's own
 * test, so a field the contract gains should fail here until it is decided what it decodes to. */
const ROW = {
  item_id: 'ENT@a',
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
}

describe('ProjectedOccurrenceSchema', () => {
  it('decodes a plain string style value (match/range mode)', () => {
    const decoded = Schema.decodeUnknownSync(ProjectedOccurrenceSchema)({
      ...ROW, style: { node_color: 'critical' },
    })
    expect(decoded.style.node_color).toBe('critical')
  })

  it('decodes a scale-mode {position, tokens} style value — regression: this real backend shape (captured live from element-dependents execution) previously failed decoding entirely because the schema only accepted strings', () => {
    const decoded = Schema.decodeUnknownSync(ProjectedOccurrenceSchema)({
      ...ROW,
      item_id: 'ACT@1712870400.Pp8Qq8.developer',
      membership: 'expanded',
      style: { node_color: { position: 0.3333333333333333, tokens: ['heat-near', 'heat-far'] } },
    })
    expect(decoded.style.node_color).toEqual({ position: 0.3333333333333333, tokens: ['heat-near', 'heat-far'] })
  })

  it('keeps a derived connection’s evidence, which the six-field decoder stripped', () => {
    // Captured from a derived-traversal execution: the row arrived with certainty, hop count and
    // witness ids, and an effect struct that had not declared them dropped all three on decode —
    // leaving the overlay unable to tell a derived edge from a modelled one.
    const decoded = Schema.decodeUnknownSync(ProjectedOccurrenceSchema)({
      ...ROW,
      item_id: 'DRV@a-b',
      item_kind: 'connection',
      connection_type: 'archimate-serving',
      source_id: 'ENT@a',
      target_id: 'ENT@b',
      certainty: 'potential',
      hops: 2,
      via_connection_ids: ['CON@a-x', 'CON@x-b'],
    })
    expect(decoded.certainty).toBe('potential')
    expect(decoded.hops).toBe(2)
    expect(decoded.via_connection_ids).toEqual(['CON@a-x', 'CON@x-b'])
  })
})
