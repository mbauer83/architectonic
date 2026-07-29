import { describe, expect, it } from 'vitest'
import { mkTracePattern } from '../../../domain/viewpointTracePattern'
import {
  addBranchEdge, addPattern, addShortcut, declaredEdgeCount, removeAt, removeBranchEdge,
  replaceAt, samplePreviewTable, setBranchesInline, setBranchesRef, setLeafDerived, setLeafNone,
  toggleMember, updateBranchEdge,
} from '../ViewpointTracePatternEditor.helpers'

describe('array helpers', () => {
  it('removeAt / replaceAt are pure and index-correct', () => {
    expect(removeAt(['a', 'b', 'c'], 1)).toEqual(['a', 'c'])
    expect(replaceAt(['a', 'b', 'c'], 2, 'z')).toEqual(['a', 'b', 'z'])
  })

  it('toggleMember adds then removes', () => {
    expect(toggleMember(['goal'], 'outcome')).toEqual(['goal', 'outcome'])
    expect(toggleMember(['goal', 'outcome'], 'goal')).toEqual(['outcome'])
  })

  it('addPattern appends', () => {
    const p = mkTracePattern()
    expect(addPattern([], p)).toEqual([p])
  })
})

describe('branches mode', () => {
  it('a fresh pattern is inline-empty; switching from ref back to inline seeds one edge', () => {
    const fresh = mkTracePattern()
    expect(fresh.branches.kind).toBe('inline')
    if (fresh.branches.kind === 'inline') expect(fresh.branches.edges).toHaveLength(0)

    const ref = setBranchesRef(fresh, 'motivation')
    expect(ref.branches).toEqual({ kind: 'ref', ref: 'motivation' })

    const reInline = setBranchesInline(ref)
    if (reInline.branches.kind === 'inline') expect(reInline.branches.edges).toHaveLength(1)
  })

  it('addBranchEdge only applies to inline branches; a {ref} is untouched', () => {
    const ref = setBranchesRef(mkTracePattern(), 'x')
    expect(addBranchEdge(ref)).toBe(ref)

    const inline = addBranchEdge(mkTracePattern())
    if (inline.branches.kind === 'inline') expect(inline.branches.edges).toHaveLength(1)
  })

  it('updateBranchEdge / removeBranchEdge target the right index', () => {
    let p = addBranchEdge(addBranchEdge(mkTracePattern()))
    if (p.branches.kind !== 'inline') throw new Error('inline expected')
    expect(p.branches.edges).toHaveLength(2)
    const first = p.branches.edges[0]
    p = updateBranchEdge(p, 0, { ...first, connection: 'archimate-influence' })
    if (p.branches.kind === 'inline') expect(p.branches.edges[0].connection).toBe('archimate-influence')
    p = removeBranchEdge(p, 0)
    if (p.branches.kind === 'inline') expect(p.branches.edges).toHaveLength(1)
  })
})

describe('leaf and shortcuts', () => {
  it('setLeafDerived defaults to the realizer registry, setLeafNone reverts', () => {
    const derived = setLeafDerived(mkTracePattern())
    expect(derived.leaf.kind).toBe('derived-reachability')
    if (derived.leaf.kind === 'derived-reachability') expect(derived.leaf.endpoint.kind).toBe('registry')
    expect(setLeafNone(derived).leaf).toEqual({ kind: 'none' })
  })

  it('addShortcut appends a diagnostic edge', () => {
    expect(addShortcut(mkTracePattern()).shortcuts).toHaveLength(1)
  })

  it('declaredEdgeCount sums inline branch edges and shortcuts; a {ref} contributes zero', () => {
    let p = addBranchEdge(addBranchEdge(mkTracePattern())) // 2 inline edges
    p = addShortcut(p) // + 1 shortcut
    expect(declaredEdgeCount(p)).toBe(3)
    expect(declaredEdgeCount(setBranchesRef(mkTracePattern(), 'x'))).toBe(0)
  })
})

describe('sample preview (I-G5: two cell shapes)', () => {
  it('shows one authoritative gap cell and one diagnostic none_observed cell', () => {
    const table = samplePreviewTable()
    const [motivationName, authoritative] = table.rows[0].pattern_results[0]
    const [, diagnostic] = table.rows[0].pattern_results[1]
    expect(motivationName).toBe('motivation')
    expect(authoritative.role).toBe('authoritative')
    if (authoritative.role === 'authoritative') expect(authoritative.verdict).toBe('gap')
    expect(diagnostic.role).toBe('diagnostic')
    if (diagnostic.role === 'diagnostic') expect(diagnostic.observation).toBe('none_observed')
  })
})
