/**
 * Which diagrams a candidate may be drawn on, and whether a type draws an element again, are read from the
 * diagram-type catalogue — not from the spelling of a type's name, which four candidate views and the shared
 * canvas each tested with `startsWith('archimate')`.
 */
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { Effect } from 'effect'
import type { DiagramList, DiagramSummary, DiagramTypeSummary } from '../../../domain'
import { typeCan } from '../../../domain/diagramTypeCapabilities'
import { diagramsHostingCandidates, useDiagramTypeCapabilities } from '../useDiagramTypeCapabilities'

const kind = (key: string, hosts: boolean, again = hosts): DiagramTypeSummary => ({
  key, label: key, description: '', hosts_candidates: hosts, draws_occurrences: again, arranges_on_canvas: again,
})
const TYPES = [kind('archimate-layered', true), kind('c4-container', false), kind('own-sketch', true, false)]

const diagram = (id: string, diagramType: string): DiagramSummary => ({
  artifact_id: id, diagram_type: diagramType, name: id, version: '1', status: 'active', path: `${id}.puml`,
  is_global: false, baseline_standing: { kind: 'enterprise-baseline' },
})
const LISTED: DiagramList = {
  total: 4,
  items: [
    diagram('ARC@1.a', 'archimate-layered'), diagram('C4@1.b', 'c4-container'),
    diagram('OWN@1.c', 'own-sketch'), diagram('MTX@1.d', 'matrix'),
  ],
}

const service = (types: Effect.Effect<DiagramTypeSummary[], never> | null) => ({
  listDiagrams: () => Effect.succeed(LISTED),
  listDiagramTypes: () => types ?? Effect.die('the catalogue cannot be read'),
})

describe('a capability, as the catalogue states it', () => {
  it('is the served flag of the type', () => {
    expect(typeCan(TYPES, 'archimate-layered', 'hosts_candidates')).toBe(true)
    expect(typeCan(TYPES, 'c4-container', 'hosts_candidates')).toBe(false)
    expect(typeCan(TYPES, 'own-sketch', 'draws_occurrences')).toBe(false)
  })

  it('is false for a type the catalogue does not list, or none', () => {
    expect(typeCan(TYPES, 'matrix', 'hosts_candidates')).toBe(false)
    expect(typeCan(TYPES, undefined, 'draws_occurrences')).toBe(false)
  })
})

describe('the diagrams a candidate may be drawn on', () => {
  it('are those whose type hosts candidates, whatever the type is called', async () => {
    const hosting = await diagramsHostingCandidates(service(Effect.succeed(TYPES)))
    expect(hosting.map((one) => one.artifact_id)).toEqual(['ARC@1.a', 'OWN@1.c'])
  })

  it('are none while the catalogue cannot be read', async () => {
    expect(await diagramsHostingCandidates(service(null))).toEqual([])
  })
})

describe('a capability asked of the catalogue as it loads', () => {
  it('is withheld until the catalogue answers, then read from it', async () => {
    const can = useDiagramTypeCapabilities(service(Effect.succeed(TYPES)))
    expect(can('archimate-layered', 'draws_occurrences')).toBe(false)
    await nextTick()
    await Promise.resolve()
    expect(can('archimate-layered', 'draws_occurrences')).toBe(true)
    expect(can('c4-container', 'draws_occurrences')).toBe(false)
  })
})
