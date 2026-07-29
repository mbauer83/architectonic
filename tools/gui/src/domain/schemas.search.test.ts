import { describe, it, expect } from 'vitest'
import { Schema, Either } from 'effect'
import { SearchHitSchema, SearchResultSchema } from './schemas'

const ENTITY_HIT = {
  score: 1.5,
  record_type: 'entity',
  artifact_id: 'ENT@123.foo',
  name: 'Foo',
  artifact_type: 'archimate-application-component',
  status: 'draft',
  path: 'path/to/foo.md',
  domain: 'application',
}

const DOCUMENT_HIT = {
  score: 0.9,
  record_type: 'document',
  artifact_id: 'STD@456.general-coding-guidelines',
  name: 'General Coding Guidelines',
  artifact_type: 'document',
  status: 'approved',
  path: 'path/to/doc.md',
}

const DIAGRAM_HIT = {
  score: 0.7,
  record_type: 'diagram',
  artifact_id: 'DIA@789.my-diagram',
  name: 'My Diagram',
  artifact_type: 'c4',
  status: 'draft',
  path: 'path/to/diagram.md',
}

const CONNECTION_HIT = {
  score: 0.5,
  record_type: 'connection',
  artifact_id: 'CONN@abc.conn',
  name: '',
  artifact_type: 'archimate-serving',
  status: 'draft',
  path: 'path/to/conn.md',
  source: 'ENT@123.foo',
  target: 'ENT@999.bar',
}

const decode = Schema.decodeUnknownSync(SearchHitSchema)

describe('SearchHitSchema', () => {
  it('decodes an entity hit', () => {
    const result = decode(ENTITY_HIT)
    expect(result.record_type).toBe('entity')
    expect(result.name).toBe('Foo')
  })

  it('decodes a document hit', () => {
    const result = decode(DOCUMENT_HIT)
    expect(result.record_type).toBe('document')
    expect(result.name).toBe('General Coding Guidelines')
  })

  it('decodes a diagram hit', () => {
    const result = decode(DIAGRAM_HIT)
    expect(result.record_type).toBe('diagram')
  })

  it('decodes a connection hit', () => {
    const result = decode(CONNECTION_HIT)
    expect(result.record_type).toBe('connection')
    expect(result.source).toBe('ENT@123.foo')
  })

  it('decodes an assurance-node placeholder hit', () => {
    const hit = { ...ENTITY_HIT, record_type: 'assurance-node' }
    const result = decode(hit)
    expect(result.record_type).toBe('assurance-node')
  })

  it('throws on an unknown record_type', () => {
    const hit = { ...ENTITY_HIT, record_type: 'unknown-future-type' }
    expect(() => decode(hit)).toThrow()
  })
})

describe('SearchResultSchema with mixed hits', () => {
  it('decodes a response containing entity + document + diagram hits', () => {
    const raw = {
      query: 'coding guidelines',
      hits: [ENTITY_HIT, DOCUMENT_HIT, DIAGRAM_HIT],
    }
    const result = Schema.decodeUnknownSync(SearchResultSchema)(raw)
    expect(result.hits).toHaveLength(3)
    expect(result.hits.map((h) => h.record_type)).toEqual(['entity', 'document', 'diagram'])
  })
})

describe('per-hit decoding fallback (simulating adapter logic)', () => {
  it('skips unrecognised hits without throwing, preserving known hits', () => {
    const decodeEither = Schema.decodeUnknownEither(SearchHitSchema)
    const rawHits: unknown[] = [
      ENTITY_HIT,
      { record_type: 'alien', artifact_id: 'x', name: 'x', status: 'x', path: 'x', score: 0 },
      DOCUMENT_HIT,
    ]

    const decoded = rawHits.flatMap((h) => {
      const result = decodeEither(h)
      return Either.isLeft(result) ? [] : [result.right]
    })

    expect(decoded).toHaveLength(2)
    expect(decoded[0].record_type).toBe('entity')
    expect(decoded[1].record_type).toBe('document')
  })
})
