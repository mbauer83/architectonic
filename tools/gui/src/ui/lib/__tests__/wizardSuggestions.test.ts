import { describe, it, expect } from 'vitest'
import {
  legalConnectionPairs,
  nameSimilarity,
  phraseSuggestion,
  buildWizardSuggestions,
  buildChainSuggestions,
  connectionKindRank,
  type PermittedConnectionsByPeer,
} from '../wizardSuggestions'
import type { EntityDisplayInfo } from '../../../domain'

const entity = (artifact_id: string, name: string): EntityDisplayInfo => ({
  artifact_id, name, artifact_type: 'outcome', domain: 'motivation', subdomain: '',
  status: 'draft', display_alias: artifact_id, element_type: 'outcome', element_label: 'Outcome', diagram_internal: false,
})

describe('legalConnectionPairs', () => {
  it('flattens outgoing/incoming/symmetric records into one list, tagged by direction', () => {
    // Records are keyed by TARGET type, value arrays hold legal CONNECTION types for that
    // target (see `_classify_connections` in `type_guidance.py`) — not the other way around.
    const classification: PermittedConnectionsByPeer = {
      outgoing: { outcome: ['realizes'], requirement: ['requires'], principle: ['requires'] },
      incoming: { driver: ['serves'] },
      symmetric: {},
    }
    expect(legalConnectionPairs(classification)).toEqual([
      { direction: 'outgoing', connectionType: 'realizes', targetType: 'outcome' },
      { direction: 'outgoing', connectionType: 'requires', targetType: 'requirement' },
      { direction: 'outgoing', connectionType: 'requires', targetType: 'principle' },
      { direction: 'incoming', connectionType: 'serves', targetType: 'driver' },
    ])
  })

  it('returns an empty list when nothing is legal', () => {
    expect(legalConnectionPairs({ outgoing: {}, incoming: {}, symmetric: {} })).toEqual([])
  })
})

describe('nameSimilarity', () => {
  it('scores identical names at 1', () => {
    expect(nameSimilarity('Reduce Onboarding Friction', 'Reduce Onboarding Friction')).toBe(1)
  })

  it('scores completely unrelated names at 0', () => {
    expect(nameSimilarity('Reduce Onboarding Friction', 'Promote Artifacts')).toBe(0)
  })

  it('scores partial word overlap between 0 and 1', () => {
    const score = nameSimilarity('Reduce Onboarding Friction', 'Onboarding Friction Survey')
    expect(score).toBeGreaterThan(0)
    expect(score).toBeLessThan(1)
  })

  it('ignores short filler words so they never inflate the score', () => {
    expect(nameSimilarity('A to Do', 'Or an Of')).toBe(0)
  })
})

describe('phraseSuggestion', () => {
  it('renders a one-line sentence with the connection type as a readable verb', () => {
    expect(phraseSuggestion('Goal X', 'realizes', 'Outcome Y')).toBe('Goal X probably realizes Outcome Y')
  })

  it('replaces hyphens/underscores in the connection type with spaces', () => {
    expect(phraseSuggestion('X', 'is-realized-by', 'Y')).toBe('X probably is realized by Y')
  })
})

describe('buildWizardSuggestions', () => {
  const source = { id: 'GOL@1.a.x', name: 'Reduce Onboarding Friction', domain: 'motivation' }

  it('picks the best-matching candidate per legal pair and caps the combined list', () => {
    const pairs = [
      { direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' },
      { direction: 'outgoing' as const, connectionType: 'requires', targetType: 'requirement' },
    ]
    const candidatesByType = new Map([
      ['outcome', [entity('o1', 'Unrelated'), entity('o2', 'Reduce Onboarding Friction Outcome')]],
      ['requirement', [entity('r1', 'Some Requirement')]],
    ])
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByType, 5)
    expect(suggestions).toHaveLength(2)
    expect(suggestions[0].targetId).toBe('o2')
    expect(suggestions[0].sourceId).toBe('GOL@1.a.x')
  })

  it('flips endpoints for an incoming pair so sourceId/targetId reflect the real connection direction', () => {
    const pairs = [{ direction: 'incoming' as const, connectionType: 'serves', targetType: 'driver' }]
    const candidatesByType = new Map([['driver', [entity('d1', 'Driver Name')]]])
    const [suggestion] = buildWizardSuggestions(source, pairs, candidatesByType, 5)
    expect(suggestion.sourceId).toBe('d1')
    expect(suggestion.targetId).toBe('GOL@1.a.x')
  })

  it('caps the result to the requested number, keeping the highest-scoring pairs', () => {
    const pairs = [
      { direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' },
      { direction: 'outgoing' as const, connectionType: 'requires', targetType: 'requirement' },
      { direction: 'outgoing' as const, connectionType: 'serves', targetType: 'driver' },
    ]
    const candidatesByType = new Map([
      ['outcome', [entity('o1', 'Reduce Onboarding Friction')]],
      ['requirement', [entity('r1', 'Reduce Onboarding Friction')]],
      ['driver', [entity('d1', 'Totally Unrelated')]],
    ])
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByType, 2)
    expect(suggestions).toHaveLength(2)
    expect(suggestions.map((s) => s.targetId)).not.toContain('d1')
  })

  it('skips a legal pair with no available candidates', () => {
    const pairs = [{ direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' }]
    const suggestions = buildWizardSuggestions(source, pairs, new Map(), 5)
    expect(suggestions).toHaveLength(0)
  })

  it('nudges a graph-proximity neighbor ahead of an equally-unrelated-by-name candidate', () => {
    const pairs = [{ direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' }]
    // Neither candidate shares a word with the source name, so name similarity alone ties at 0 —
    // the proximity boost is the only thing that can break the tie.
    const candidatesByType = new Map([['outcome', [entity('o1', 'Zzz Zzz'), entity('o2', 'Qqq Qqq')]]])
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByType, 5, new Set(['o2']))
    expect(suggestions[0].targetId).toBe('o2')
  })

  it('is a pure tiebreaker: never overrides a genuinely better name match', () => {
    const pairs = [{ direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' }]
    const candidatesByType = new Map([
      ['outcome', [entity('o1', 'Reduce Onboarding Friction Outcome'), entity('o2', 'Totally Unrelated')]],
    ])
    // o2 is a "neighbor" but o1's name match is decisive — proximity must not flip the outcome.
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByType, 5, new Set(['o2']))
    expect(suggestions[0].targetId).toBe('o1')
  })

  it('defaults to no proximity boost when the parameter is omitted', () => {
    const pairs = [{ direction: 'outgoing' as const, connectionType: 'realizes', targetType: 'outcome' }]
    const candidatesByType = new Map([['outcome', [entity('o1', 'Reduce Onboarding Friction Outcome')]]])
    const suggestions = buildWizardSuggestions(source, pairs, candidatesByType, 5)
    expect(suggestions).toHaveLength(1)
  })
})

describe('buildChainSuggestions', () => {
  const source = { id: 'DRV@1.a.d', name: 'Regulatory Pressure', domain: 'motivation' }
  const pairs = [
    { direction: 'outgoing' as const, connectionType: 'archimate-association', targetType: 'stakeholder' },
    { direction: 'incoming' as const, connectionType: 'archimate-influence', targetType: 'assessment' },
  ]

  it('connects the source to a spine anchor of a legal peer type, most recent anchor first', () => {
    const anchors = [
      { id: 'STK@1.a.s1', name: 'Old Stakeholder', type: 'stakeholder' },
      { id: 'STK@1.a.s2', name: 'Compliance Officer', type: 'stakeholder' },
    ]
    const suggestions = buildChainSuggestions(source, pairs, anchors, 3)
    expect(suggestions[0].targetId).toBe('STK@1.a.s2')
    expect(suggestions[0].connectionType).toBe('archimate-association')
    expect(suggestions[1].targetId).toBe('STK@1.a.s1')
  })

  it('flips endpoints for incoming pairs (anchor is the real connection source)', () => {
    const anchors = [{ id: 'ASS@1.a.a1', name: 'Untraceable Actions', type: 'assessment' }]
    const [suggestion] = buildChainSuggestions(source, pairs, anchors, 3)
    expect(suggestion.sourceId).toBe('ASS@1.a.a1')
    expect(suggestion.targetId).toBe(source.id)
  })

  it('skips anchors with no legal pair and the source itself, and honors the cap', () => {
    const anchors = [
      { id: source.id, name: source.name, type: 'driver' },
      { id: 'GOL@1.a.g1', name: 'Some Goal', type: 'goal' },
      { id: 'STK@1.a.s1', name: 'S1', type: 'stakeholder' },
      { id: 'STK@1.a.s2', name: 'S2', type: 'stakeholder' },
    ]
    expect(buildChainSuggestions(source, pairs, anchors, 1)).toHaveLength(1)
    expect(buildChainSuggestions(source, pairs, anchors, 5).map((s) => s.targetId))
      .toEqual(['STK@1.a.s2', 'STK@1.a.s1'])
  })

  it('returns nothing for an empty anchor list', () => {
    expect(buildChainSuggestions(source, pairs, [], 3)).toHaveLength(0)
  })
})

describe('connection-kind guidance', () => {
  const source = { id: 'PRC@1.a.p', name: 'Review Audit Trail', domain: 'common' }

  it('ranks meaningful kinds ahead of the generic association', () => {
    expect(connectionKindRank('archimate-realization')).toBeLessThan(connectionKindRank('archimate-access'))
    expect(connectionKindRank('archimate-triggering')).toBeLessThan(connectionKindRank('archimate-association'))
    expect(connectionKindRank('some-unknown-kind')).toBeLessThan(connectionKindRank('archimate-association'))
  })

  it('chain suggestions pick the strongest legal relation, not the first listed', () => {
    // A process↔service peer where both association and realization are legal — the wizard
    // must lead with "realizes", the behavioural spine relation.
    const pairs = [
      { direction: 'outgoing' as const, connectionType: 'archimate-association', targetType: 'service' },
      { direction: 'outgoing' as const, connectionType: 'archimate-realization', targetType: 'service' },
    ]
    const anchors = [{ id: 'SRV@1.a.s', name: 'Audit Logging Service', type: 'service' }]
    const [suggestion] = buildChainSuggestions(source, pairs, anchors, 3)
    expect(suggestion.connectionType).toBe('archimate-realization')
    expect(suggestion.summary).toContain('probably realizes')
  })

  it('pool suggestions offer one relation per peer — the strongest — instead of near-duplicates', () => {
    const pairs = [
      { direction: 'outgoing' as const, connectionType: 'archimate-association', targetType: 'event' },
      { direction: 'outgoing' as const, connectionType: 'archimate-triggering', targetType: 'event' },
    ]
    const candidates = new Map([['event', [entity('e1', 'Audit Event Raised')]]])
    const suggestions = buildWizardSuggestions(source, pairs, candidates, 5)
    expect(suggestions).toHaveLength(1)
    expect(suggestions[0].connectionType).toBe('archimate-triggering')
  })

  it('a step chainPreference overrides the global kind ranking for chain suggestions', () => {
    // function × process: aggregation (subdivision) must beat the globally higher-ranked
    // triggering when the step declares its intent.
    const pairs = [
      { direction: 'incoming' as const, connectionType: 'archimate-triggering', targetType: 'process' },
      { direction: 'incoming' as const, connectionType: 'archimate-aggregation', targetType: 'process' },
    ]
    const anchors = [{ id: 'PRC@1.a.parent', name: 'Review Audit Trail', type: 'process' }]
    const fn = { id: 'FUN@1.a.f', name: 'Collect Audit Evidence', domain: 'common' }
    const [plain] = buildChainSuggestions(fn, pairs, anchors, 3)
    expect(plain.connectionType).toBe('archimate-triggering')
    const [preferred] = buildChainSuggestions(fn, pairs, anchors, 3, ['archimate-aggregation'])
    expect(preferred.connectionType).toBe('archimate-aggregation')
    expect(preferred.summary).toContain('probably aggregates')
  })

  it('phrases known kinds as natural verbs', () => {
    expect(phraseSuggestion('A', 'archimate-access', 'B')).toBe('A probably accesses B')
    expect(phraseSuggestion('A', 'archimate-flow', 'B')).toBe('A probably flows to B')
    expect(phraseSuggestion('A', 'archimate-association', 'B')).toBe('A probably is associated with B')
  })
})

describe('type-diverse chain anchor selection', () => {
  const process = { id: 'PRC@1.a.new', name: 'Handle Audit Request', domain: 'common' }
  const pairs = [
    { direction: 'incoming' as const, connectionType: 'archimate-assignment', targetType: 'role' },
    { direction: 'outgoing' as const, connectionType: 'archimate-access', targetType: 'business-object' },
    { direction: 'outgoing' as const, connectionType: 'archimate-triggering', targetType: 'process' },
  ]

  it('a run of recent same-type anchors cannot crowd out the object and role relations', () => {
    // Oldest → newest: role, business-object, then three processes. Recency-only selection
    // with cap 4 would pick 3 processes + the object and drop the role's assignment.
    const anchors = [
      { id: 'ROL@1.a.r', name: 'Audit Reviewer', type: 'role' },
      { id: 'BOB@1.a.o', name: 'Audit Record', type: 'business-object' },
      { id: 'PRC@1.a.p1', name: 'P1', type: 'process' },
      { id: 'PRC@1.a.p2', name: 'P2', type: 'process' },
      { id: 'PRC@1.a.p3', name: 'P3', type: 'process' },
    ]
    const suggestions = buildChainSuggestions(process, pairs, anchors, 4)
    const kinds = suggestions.map((s) => s.connectionType)
    expect(kinds).toContain('archimate-assignment')
    expect(kinds).toContain('archimate-access')
    expect(kinds.filter((k) => k === 'archimate-triggering')).toHaveLength(2)
  })

  it('backfills remaining slots with same-type anchors after every type had its turn', () => {
    const anchors = [
      { id: 'PRC@1.a.p1', name: 'P1', type: 'process' },
      { id: 'PRC@1.a.p2', name: 'P2', type: 'process' },
    ]
    const suggestions = buildChainSuggestions(process, pairs, anchors, 4)
    expect(suggestions.map((s) => s.targetId === process.id ? s.sourceId : s.targetId).sort())
      .toEqual(['PRC@1.a.p1', 'PRC@1.a.p2'])
  })
})
