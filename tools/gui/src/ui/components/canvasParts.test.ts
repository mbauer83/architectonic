import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import { containedTypes, partsTypes } from './canvasParts'

describe('what a container element may hold', () => {
  it('is every type reached from it by a relation of the containment kind, and no other', () => {
    const outgoing = {
      'business-object': ['comp', 'assoc'],
      role: ['assoc'],
      'data-object': ['agg'],
    }
    expect([...containedTypes(outgoing, new Set(['comp', 'agg']))]).toEqual(['business-object', 'data-object'])
  })

  it('asks the ontology from the container type and the diagram type for the relations that contain', async () => {
    const svc = {
      getOntologyClassification: () => Effect.succeed({
        source_type: 'business-object', incoming: {}, symmetric: {},
        outgoing: { 'business-object': ['x-composition'], role: ['x-serving'] },
      }),
      getDiagramTypeConnectionTypes: () => Effect.succeed([
        { connection_type: 'x-composition', relationship_kind: 'containment' },
        { connection_type: 'x-serving', relationship_kind: 'dependency' },
      ]),
    }
    expect([...await partsTypes(svc, 'layered', 'business-object')]).toEqual(['business-object'])
  })
})
