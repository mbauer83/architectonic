import { describe, it, expect } from 'vitest'
import { claimedMemberIds, withoutEmptyGroups, type AuthoredGrouping } from './authoredGrouping'

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
