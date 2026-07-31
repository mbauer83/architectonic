/**
 * Filing and authorship, two levels deep with counts.
 *
 * A group files analyses; an analysis authors nodes, and the tree says how many rather than listing
 * them — the architecture nav shows groups and domains with counts and sends you to the table for
 * the entities, and this mirrors that. Listing nodes here turned "no analysis" into a 26-entry
 * fold-out that pushed the analyses off the bottom of the sidebar.
 *
 * Participation is deliberately absent: a node counted under two analyses would read as two nodes,
 * and the second would look exactly like the copy the three-relation arrangement exists to avoid.
 */
import { describe, expect, it } from 'vitest'
import {
  NO_ANALYSIS_SCOPE,
  UNATTRIBUTED_LABEL,
  UNFILED_LABEL,
  buildFilingTree,
  type AssuranceAnalysis,
  type AssuranceGroup,
  type AssuranceTreeNode,
} from '../AssuranceFilingTree.helpers'

/* Whole records, because that is what the two collections send. The fixtures carried two or four
   fields while the routes sent five and nine, which the old looser interfaces permitted. */
const STAMPS = { created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }

const group = (fields: Pick<AssuranceGroup, 'group_id' | 'name'>): AssuranceGroup =>
  ({ description: '', ...STAMPS, ...fields })

const analysis = (
  fields: Pick<AssuranceAnalysis, 'analysis_id' | 'name' | 'method' | 'group_id'>,
): AssuranceAnalysis =>
  ({ architecture_anchor_id: '', status: 'draft', tlp: 'TLP:WHITE', ...STAMPS, ...fields })

const PLATFORM = group({ group_id: 'GRP@1.aaaa.01', name: 'Platform safety' })
const SUPPLY = group({ group_id: 'GRP@1.bbbb.02', name: 'Supply chain' })

const STPA = analysis({
  analysis_id: 'STPA@1.cccc.03',
  name: 'Key availability',
  method: 'STPA',
  group_id: PLATFORM.group_id,
})
const FMEA = analysis({
  analysis_id: 'FMEA@1.dddd.04',
  name: 'Credential backend',
  method: 'FMEA',
  group_id: null,
})

const HAZARD: AssuranceTreeNode = {
  node_id: 'HAZ@1.eeee.05',
  name: 'Key unavailable',
  node_type: 'hazard',
  analysis_id: STPA.analysis_id,
}
const FAILURE_MODE: AssuranceTreeNode = {
  node_id: 'FMD@1.ffff.06',
  name: 'Answers with a foreign secret',
  node_type: 'failure-mode',
  analysis_id: FMEA.analysis_id,
}

const labels = (nodes: readonly { label: string }[]) => nodes.map(node => node.label)

describe('buildFilingTree', () => {
  it('nests analysis under group, and stops there', () => {
    const tree = buildFilingTree([PLATFORM], [STPA], [HAZARD])

    expect(labels(tree)).toEqual(['Platform safety'])
    expect(labels(tree[0].children!)).toEqual(['Key availability'])
    expect(tree[0].children![0].children).toBeUndefined()
  })

  it('badges a group with its analyses and an analysis with its method and node count', () => {
    const tree = buildFilingTree([PLATFORM], [STPA], [HAZARD])

    expect(tree[0].badge).toBe('1')
    expect(tree[0].children![0].badge).toBe('STPA · 1')
  })

  it('counts only the nodes an analysis authored', () => {
    const tree = buildFilingTree(
      [PLATFORM], [STPA, { ...FMEA, group_id: PLATFORM.group_id }], [HAZARD, FAILURE_MODE],
    )
    const badgeFor = (name: string) =>
      tree[0].children!.find(child => child.label === name)!.badge

    expect(badgeFor('Key availability')).toBe('STPA · 1')
    expect(badgeFor('Credential backend')).toBe('FMEA · 1')
  })

  it('shows an empty group, so creating one does not look like it failed', () => {
    const tree = buildFilingTree([PLATFORM, SUPPLY], [STPA], [])

    expect(labels(tree)).toEqual(['Platform safety', 'Supply chain'])
    expect(tree[1].children).toEqual([])
  })

  it('gives unfiled analyses a home of their own', () => {
    /* An analysis is worth recording before anyone settles where it belongs, so unfiled is a
       normal state rather than an error. */
    const tree = buildFilingTree([PLATFORM], [STPA, FMEA], [])

    expect(labels(tree)).toEqual(['Platform safety', UNFILED_LABEL])
    expect(labels(tree[1].children!)).toEqual(['Credential backend'])
  })

  it('omits the unfiled heading when everything is filed', () => {
    /* An always-present "Unfiled" that is usually empty is a permanent reminder of nothing. */
    const tree = buildFilingTree([PLATFORM], [STPA], [])

    expect(labels(tree)).toEqual(['Platform safety'])
  })

  it('counts nodes belonging to no analysis, and does not fold them out', () => {
    /* They violate the model's own rule, so the number is worth stating — but it is a defect to go
       and fix, not a place to browse from, and it must not get more sidebar than the analyses do. */
    const stray: AssuranceTreeNode = {
      node_id: 'HAZ@1.gggg.07', name: 'Orphan', node_type: 'hazard', analysis_id: null,
    }

    const tree = buildFilingTree([], [], [stray, { ...stray, node_id: 'HAZ@1.hhhh.08' }])

    expect(labels(tree)).toEqual([UNATTRIBUTED_LABEL])
    expect(tree[0].badge).toBe('2')
    expect(tree[0].children).toBeUndefined()
  })

  it('scopes the list to the unattributed nodes by a reserved word, not a made-up id', () => {
    const stray: AssuranceTreeNode = {
      node_id: 'HAZ@1.gggg.07', name: 'Orphan', node_type: 'hazard', analysis_id: null,
    }

    const tree = buildFilingTree([], [], [stray])

    expect(tree[0].to).toEqual({ path: '/assurance', query: { analysis: NO_ANALYSIS_SCOPE } })
  })

  it('says nothing about unattributed nodes when there are none', () => {
    expect(labels(buildFilingTree([PLATFORM], [STPA], [HAZARD]))).toEqual(['Platform safety'])
  })

  it('orders groups, analyses and nodes by name', () => {
    const other = analysis({
      analysis_id: 'STPA@1.hhhh.08', name: 'Access control', method: 'STPA',
      group_id: PLATFORM.group_id,
    })

    const tree = buildFilingTree([SUPPLY, PLATFORM], [STPA, other], [])

    expect(labels(tree)).toEqual(['Platform safety', 'Supply chain'])
    expect(labels(tree[0].children!)).toEqual(['Access control', 'Key availability'])
  })

  it('routes an analysis to the browse surface scoped to it', () => {
    /* More useful than any one node, and it still works for an analysis with nothing in it yet. */
    const tree = buildFilingTree([PLATFORM], [STPA], [])

    expect(tree[0].children![0].to).toEqual({
      path: '/assurance',
      query: { analysis: STPA.analysis_id },
    })
  })

  it('falls back to the id when a record has no name', () => {
    const tree = buildFilingTree(
      [group({ group_id: PLATFORM.group_id, name: '' })],
      [{ ...STPA, name: '' }],
      [],
    )

    expect(tree[0].label).toBe(PLATFORM.group_id)
    expect(tree[0].children![0].label).toBe(STPA.analysis_id)
  })

  it('is empty for an empty store', () => {
    expect(buildFilingTree([], [], [])).toEqual([])
  })
})
