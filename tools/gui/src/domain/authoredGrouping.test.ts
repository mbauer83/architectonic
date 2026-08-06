import { describe, it, expect } from 'vitest'
import {
  claimedMemberIds, withMemberBeside, withoutEmptyGroups, type AuthoredGrouping,
} from './authoredGrouping'

const group = (label: string, ids: string[], groups?: AuthoredGrouping[]): AuthoredGrouping => ({
  label,
  'entity-ids': ids,
  ...(groups ? { groups } : {}),
})

describe('which members are already placed', () => {
  it('reports members of every box', () => {
    const claimed = claimedMemberIds([group('A', ['one']), group('B', ['two'])])

    expect([...claimed].sort()).toEqual(['one', 'two'])
  })

  it('reaches members nested inside a box', () => {
    // A member the editor lets you place twice is a member the backend silently drops from the
    // second box, so the greying-out has to see the same depth the resolver does.
    const claimed = claimedMemberIds([group('Outer', ['one'], [group('Inner', ['two'])])])

    expect([...claimed].sort()).toEqual(['one', 'two'])
  })
})

describe('what gets sent', () => {
  it('drops a box with no members', () => {
    expect(withoutEmptyGroups([group('Named but empty', [])])).toEqual([])
  })

  it('keeps a box whose only content is a populated subgroup', () => {
    const sent = withoutEmptyGroups([group('Outer', [], [group('Inner', ['one'])])])

    expect(sent).toHaveLength(1)
    expect(sent[0].groups).toHaveLength(1)
  })

  it('drops an empty subgroup while keeping its parent', () => {
    const sent = withoutEmptyGroups([group('Outer', ['one'], [group('Inner', [])])])

    expect(sent).toEqual([{ label: 'Outer', 'entity-ids': ['one'] }])
  })

  it('never sends a stereotype — the look is derived from the members', () => {
    const sent = withoutEmptyGroups([{ label: 'A', 'entity-ids': ['one'], stereotype: 'MotivationGrouping' }])

    expect(sent[0]).not.toHaveProperty('stereotype')
  })
})

describe('a grouping with no members yet', () => {
  it('survives editing, so a box can be named before it is filled', () => {
    // The editor creates an empty box first; dropping it on every keystroke would make that
    // impossible. Only the payload prunes.
    const groups: AuthoredGrouping[] = [{ label: 'Forces', 'entity-ids': [] }]

    expect(claimedMemberIds(groups).size).toBe(0)
    expect(withoutEmptyGroups(groups)).toEqual([])
  })
})

describe('joining the box a drawing lives in', () => {
  it('puts the new member in the box holding the host', () => {
    // Reached through a box, a neighbour that lands outside it is not what the click offered.
    const placed = withMemberBeside([group('Forces', ['host'])], 'host', 'newcomer')

    expect(placed[0]['entity-ids']).toEqual(['host', 'newcomer'])
  })

  it('reaches a host inside a nested box, and leaves the outer one alone', () => {
    const placed = withMemberBeside(
      [group('Outer', ['other'], [group('Inner', ['host'])])], 'host', 'newcomer',
    )

    expect(placed[0]['entity-ids']).toEqual(['other'])
    expect(placed[0].groups?.[0]['entity-ids']).toEqual(['host', 'newcomer'])
  })

  it('places nothing when the host is in no box', () => {
    const groups = [group('Forces', ['someone-else'])]

    expect(withMemberBeside(groups, 'loose-host', 'newcomer')).toEqual(groups)
  })

  it('does not add a member the box already holds', () => {
    const placed = withMemberBeside([group('Forces', ['host', 'newcomer'])], 'host', 'newcomer')

    expect(placed[0]['entity-ids']).toEqual(['host', 'newcomer'])
  })

  it('leaves a box that does not hold the host untouched', () => {
    const placed = withMemberBeside(
      [group('A', ['host']), group('B', ['other'])], 'host', 'newcomer',
    )

    expect(placed[1]['entity-ids']).toEqual(['other'])
  })
})
