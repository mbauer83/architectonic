import { describe, expect, it } from 'vitest'
import { parseDiagramLocalId } from './diagramLocalIds'

/**
 * The grammar of a diagram-owned construct's identifier, and the reason it has to be read rather
 * than passed through: the local part contains a slash, a slash ends a URL path segment, and the
 * server decodes `%2F` back before routing. `/api/entities/GSN@…%23nodes%2Fg11` therefore matches no
 * route and answers 404 — which is what left the GSN sidebar with no detail panel.
 */

const GSN_NODE = 'GSN@1781338120.3U4cRc.assurance-case-confidential-assurance-store-gsn#nodes/g11'

describe('a diagram-owned construct', () => {
  it('splits into the three parts its address needs', () => {
    expect(parseDiagramLocalId(GSN_NODE)).toEqual({
      diagramId: 'GSN@1781338120.3U4cRc.assurance-case-confidential-assurance-store-gsn',
      entityType: 'nodes',
      localId: 'g11',
    })
  })

  it('keeps the dots and the epoch-random key of the host diagram intact', () => {
    // The diagram id is itself structured; a parser that split on the wrong delimiter would take
    // the artifact type or the random key with it and address a diagram that does not exist.
    const parsed = parseDiagramLocalId(GSN_NODE)
    expect(parsed?.diagramId.startsWith('GSN@1781338120.')).toBe(true)
    expect(parsed?.diagramId).not.toContain('#')
  })
})

describe('everything that is not one', () => {
  it('reads an ordinary artifact id as not diagram-local', () => {
    expect(parseDiagramLocalId('REQ@1712870400.Kk6Ll6.verified-unique-identifiers')).toBeNull()
  })

  it('refuses a composite id with no local part, rather than guessing at one', () => {
    // A request built from a guess cannot be answered, and the 404 it earns would be blamed on the
    // server. Refusing here keeps the caller on the address that at least exists.
    expect(parseDiagramLocalId('GSN@1781338120.3U4cRc.case#')).toBeNull()
    expect(parseDiagramLocalId('GSN@1781338120.3U4cRc.case#nodes')).toBeNull()
    expect(parseDiagramLocalId('GSN@1781338120.3U4cRc.case#nodes/')).toBeNull()
    expect(parseDiagramLocalId('GSN@1781338120.3U4cRc.case#/g11')).toBeNull()
  })

  it('refuses a local part with a further slash', () => {
    // Two slashes would mean the grammar has a part this reader does not know about. Addressing it
    // as though it had two would silently request the wrong construct.
    expect(parseDiagramLocalId('GSN@1781338120.3U4cRc.case#nodes/sub/g11')).toBeNull()
  })

  it('treats a leading hash as not an identifier at all', () => {
    expect(parseDiagramLocalId('#nodes/g11')).toBeNull()
  })

  it('refuses a second hash, symmetrically with a second slash', () => {
    // Neither separator may appear inside the local id. An extra one means a grammar this reader
    // does not know about, and the two are refused the same way so there is one rule, not two.
    expect(parseDiagramLocalId('GSN@1.a.case#nodes/g11#extra')).toBeNull()
  })
})
