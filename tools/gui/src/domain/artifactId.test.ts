import { describe, expect, it } from 'vitest'
import { connectionId, connectionParts, isEntityId, stableConnectionId, stableEntityId } from './artifactId'

const SOURCE = 'PRC@1712870400.0Rz5Ex.promote-artifacts'
const TARGET = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'

describe('artifact identity', () => {
  it('writes a connection id and reads it back into the same parts', () => {
    const id = connectionId(SOURCE, 'archimate-access', TARGET)
    expect(connectionParts(id)).toEqual({ source: SOURCE, type: 'archimate-access', target: TARGET })
    expect(stableConnectionId(id)).toBe('PRC@1712870400.0Rz5Ex---SRV@1712870400.Uv9Wx9@@archimate-access')
  })

  it('reads nothing from what is not a connection id, and leaves it as it is', () => {
    expect(connectionParts(SOURCE)).toBeNull()
    expect(connectionParts('a@@b')).toBeNull()
    expect(stableConnectionId('a@@b')).toBe('a@@b')
  })

  it('tells an entity id from another reference', () => {
    expect([SOURCE, stableEntityId(SOURCE), '$ref:queue', 'occ-architect-team-b'].map(isEntityId))
      .toEqual([true, true, false, false])
  })
})
