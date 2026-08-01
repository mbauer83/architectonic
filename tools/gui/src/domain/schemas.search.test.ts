import { describe, it, expect } from 'vitest'
import { Schema, Either } from 'effect'
import { ArtifactSearchHitSchema, SearchHitSchema, SearchResultSchema } from './schemas'

const ENTITY_HIT = {
  score: 1.5,
  record_type: 'entity',
  artifact_id: 'ENT@123.foo',
  name: 'Foo',
  artifact_type: 'archimate-application-component',
  status: 'draft',
  path: 'path/to/foo.md',
  // Sent on every hit; the schema declared it nowhere, so it was invisible to every fixture too.
  last_updated: '2026-07-01',
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
  last_updated: '2026-07-01',
}

const DIAGRAM_HIT = {
  score: 0.7,
  record_type: 'diagram',
  artifact_id: 'DIA@789.my-diagram',
  name: 'My Diagram',
  artifact_type: 'c4',
  status: 'draft',
  path: 'path/to/diagram.md',
  last_updated: '2026-07-01',
}

const CONNECTION_HIT = {
  score: 0.5,
  record_type: 'connection',
  artifact_id: 'CONN@abc.conn',
  name: '',
  artifact_type: 'archimate-serving',
  status: 'draft',
  path: 'path/to/conn.md',
  last_updated: null,
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

  it('refuses an assurance-node hit, which this route cannot return', () => {
    /* It used to accept one, on a `record_type` literal added as a placeholder for a consumption that
       happened at a different address. The *display* search reaches the assurance store; the keyword
       search does not, and a union that accepts what a route cannot send describes nothing. */
    expect(() => decode({ ...ENTITY_HIT, record_type: 'assurance-node' })).toThrow()
  })

  it('decodes an assurance-node hit on the display search, which does return them', () => {
    const hit = {
      score: 1.0, record_type: 'assurance-node', artifact_id: 'HAZ@1.a.b',
      name: 'Uncommanded braking', status: 'draft',
      // Empty: an assurance node has no file.
      path: '', artifact_type: 'hazard',
    }
    const result = Schema.decodeUnknownSync(ArtifactSearchHitSchema)(hit)
    expect(result.record_type).toBe('assurance-node')
    expect(result.artifact_type).toBe('hazard')
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
