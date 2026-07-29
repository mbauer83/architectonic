import { describe, it, expect } from 'vitest'
import { Schema } from 'effect'
import { AuthoringGuidanceSchema } from '../authoring-guidance'

/**
 * The v2 additive `context` array (layered ancestry guidance) must decode on an entity-type
 * entry, and its absence must remain valid — the field is optional and never breaks the
 * existing create_when / never_create_when shape.
 */
const decode = Schema.decodeUnknownSync(AuthoringGuidanceSchema)

const baseEntity = {
  name: 'requirement',
  prefix: 'REQ',
  classes: ['motivation-element'],
  create_when: 'cw',
  never_create_when: 'nw',
  permitted_connections: { outgoing: {}, incoming: {}, symmetric: {} },
}

describe('AuthoringGuidanceSchema v2 context', () => {
  it('decodes an entity type carrying a composed context array', () => {
    const decoded = decode({
      entity_types: [
        { ...baseEntity, context: [{ level: 'domain', node: 'motivation', text: 'Motivation context.' }] },
      ],
    })
    expect(decoded.entity_types?.[0].context?.[0]).toEqual({
      level: 'domain',
      node: 'motivation',
      text: 'Motivation context.',
    })
  })

  it('decodes an entity type with no context field (optional)', () => {
    const decoded = decode({ entity_types: [baseEntity] })
    expect(decoded.entity_types?.[0].context).toBeUndefined()
  })
})
